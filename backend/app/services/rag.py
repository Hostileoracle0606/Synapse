import json
import logging
from collections import defaultdict
from typing import Dict, List

from app.config import get_settings
from app.database import get_notebook_chunks, hybrid_search_chunks
from app.services.graph import cosine_similarity
from app.services.processor import embed_document

logger = logging.getLogger(__name__)

try:
    from google import genai
except ImportError:  # pragma: no cover - import is exercised in integration environments
    genai = None


def get_gemini_client():
    settings = get_settings()
    if not settings.gemini_api_key or genai is None:
        return None
    return genai.Client(api_key=settings.gemini_api_key)


async def retrieve_relevant_sources(query: str, sources: List[Dict], top_k: int = 5) -> List[Dict]:
    if not sources:
        logger.info("retrieve_relevant_sources called with no sources")
        return []

    logger.info(
        "Retrieving relevant sources for query: %r (top_k=%d, sources=%d)",
        query[:80], top_k, len(sources),
    )

    notebook_id = sources[0].get("notebook_id")
    query_embedding = await embed_document(query)

    # ── No notebook_id: source-level cosine only ────────────────────────────
    if not notebook_id:
        scored_sources = []
        for source in sources:
            raw = source.get("embedding") or []
            if isinstance(raw, str):
                raw = json.loads(raw)
            emb = [float(v) for v in raw]
            if not emb:
                continue
            scored_sources.append({**source, "_score": cosine_similarity(query_embedding, emb)})
        scored_sources.sort(key=lambda item: item["_score"], reverse=True)
        result = scored_sources[:top_k]
        logger.info("Source-level retrieval (no chunks): top scores=%s", [round(s["_score"], 4) for s in result])
        return result

    settings = get_settings()
    sources_by_id = {source["id"]: dict(source) for source in sources}

    # ── Hybrid search path ──────────────────────────────────────────────────
    try:
        hybrid_chunks = await hybrid_search_chunks(
            notebook_id,
            query,
            query_embedding,
            match_count=settings.rag_max_chunks * 3,
        )
        if hybrid_chunks:
            ranked = _coerce_and_score_chunks(hybrid_chunks, query_embedding, settings, sources_by_id)
            result = ranked[:top_k]
            logger.info(
                "Hybrid retrieval complete — selected %d sources, top scores: %s",
                len(result),
                [round(s["_score"], 4) for s in result],
            )
            return result
        logger.info("Hybrid search returned empty — falling back to cosine")
    except Exception as exc:
        logger.warning("Hybrid search failed (%s) — falling back to cosine", exc)

    # ── Cosine fallback ─────────────────────────────────────────────────────
    chunks = await get_notebook_chunks(notebook_id)
    if not chunks:
        logger.warning("No chunks found for notebook %s — falling back to source-level retrieval", notebook_id)
        scored_sources = []
        for source in sources:
            raw = source.get("embedding") or []
            if isinstance(raw, str):
                raw = json.loads(raw)
            emb = [float(v) for v in raw]
            if not emb:
                continue
            scored_sources.append({**source, "_score": cosine_similarity(query_embedding, emb)})
        scored_sources.sort(key=lambda item: item["_score"], reverse=True)
        return scored_sources[:top_k]

    ranked = _coerce_and_score_chunks(chunks, query_embedding, settings, sources_by_id)
    result = ranked[:top_k]
    logger.info(
        "Cosine fallback complete — selected %d sources, top scores: %s",
        len(result),
        [round(s["_score"], 4) for s in result],
    )
    return result


def _coerce_and_score_chunks(
    chunks: list[dict],
    query_embedding: list[float],
    settings,
    sources_by_id: dict[str, dict],
) -> list[dict]:
    """Score *chunks*, group by source, and apply both chunk caps.

    Accepts chunks from either:
    - hybrid RPC results (have 'rrf_score' key) — score used directly
    - get_notebook_chunks fallback (have 'embedding') — cosine computed,
      embeddings coerced from pgvector strings if needed

    Returns sources list (each with '_selected_chunks' and '_score'), sorted
    descending by max chunk score.
    """
    scored_chunks = []
    for chunk in chunks:
        if "rrf_score" in chunk:
            score = float(chunk["rrf_score"])
        else:
            raw = chunk.get("embedding") or []
            if isinstance(raw, str):
                raw = json.loads(raw)
            emb = [float(v) for v in raw]
            score = cosine_similarity(query_embedding, emb)
        scored_chunks.append({**chunk, "_score": score})

    scored_chunks.sort(key=lambda c: c["_score"], reverse=True)

    selected_chunks_by_source: dict[str, list[dict]] = defaultdict(list)
    selected_total = 0

    for chunk in scored_chunks:
        if selected_total >= settings.rag_max_chunks:
            break
        sid = chunk["source_id"]
        if sid not in sources_by_id:
            continue
        if len(selected_chunks_by_source[sid]) >= settings.rag_max_chunks_per_source:
            continue
        selected_chunks_by_source[sid].append(chunk)
        selected_total += 1

    ranked_sources = []
    for source_id, selected in selected_chunks_by_source.items():
        source = dict(sources_by_id[source_id])
        source["_selected_chunks"] = [c["content"] for c in selected]
        source["_score"] = max(c["_score"] for c in selected)
        ranked_sources.append(source)

    ranked_sources.sort(key=lambda s: s["_score"], reverse=True)
    return ranked_sources


def _fallback_answer(query: str, relevant_sources: List[Dict]) -> Dict[str, List[str]]:
    if not relevant_sources:
        return {"content": "I do not have enough processed sources to answer that yet.", "sources_cited": []}

    bullet_lines = []
    cited = []
    for source in relevant_sources[:3]:
        cited.append(source["id"])
        selected_text = "\n".join(source.get("_selected_chunks") or [])
        snippet = (selected_text or source.get("summary") or source.get("content") or "").strip()
        bullet_lines.append("- {title}: {snippet}".format(title=source["title"], snippet=snippet[:220]))
    answer = "Answer based on the most relevant sources for: {query}\n\n{bullets}".format(
        query=query,
        bullets="\n".join(bullet_lines),
    )
    return {"content": answer, "sources_cited": cited}


async def generate_answer(query: str, relevant_sources: List[Dict], chat_history: List[Dict]) -> Dict[str, List[str]]:
    client = get_gemini_client()
    if client is None:
        logger.warning("No Gemini client — using fallback answer")
        return _fallback_answer(query, relevant_sources)

    logger.info("Generating answer for query: %r using %d sources", query[:80], len(relevant_sources))
    settings = get_settings()
    context_parts = []
    cited_ids = []
    for source in relevant_sources:
        cited_ids.append(source["id"])
        selected_text = "\n\n".join(source.get("_selected_chunks") or [])
        content_preview = (selected_text or source.get("content") or source.get("summary") or "")[:3000]
        context_parts.append("[Source: {title}]\n{content}".format(title=source["title"], content=content_preview))

    history_text = ""
    if chat_history:
        recent = chat_history[-6:]
        history_text = "\n".join("{role}: {content}".format(role=item["role"], content=item["content"]) for item in recent)

    prompt = (
        "You are a research assistant. Answer the user's question based only on the "
        "provided sources. Cite the source titles you draw from. If the sources do not "
        "contain the answer, say so.\n\n"
        "Recent conversation:\n{history}\n\nSources:\n{sources}\n\nUser question: {query}"
    ).format(
        history=history_text or "None",
        sources="\n\n---\n\n".join(context_parts),
        query=query,
    )

    response = await client.aio.models.generate_content(model=settings.gemini_model, contents=prompt)
    content = (getattr(response, "text", "") or "").strip()
    if not content:
        logger.warning("Gemini returned empty answer, falling back")
    else:
        logger.info("Answer generated (%d chars) citing %d source(s)", len(content), len(cited_ids))
    return {
        "content": content or _fallback_answer(query, relevant_sources)["content"],
        "sources_cited": cited_ids,
    }
