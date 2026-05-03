"""Hybrid grounded chat — long-context + url_context + google_search.

This replaces the previous embeddings/chunks/retrieval RAG pipeline. Instead
of chunking and retrieving, we pack the notebook's full corpus into the
prompt as long context and give Gemini two grounding tools:

- ``url_context``: lets the model re-read the notebook's source URLs at query
  time when it needs to verify or quote a passage precisely.
- ``google_search``: lets the model fetch fresh information for questions
  outside the notebook's corpus (e.g. post-cutoff events).

The system prompt instructs the model to prefer the local corpus and only
reach for tools when the corpus is insufficient.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from app.config import get_settings
from app.services._gemini import get_genai_client, get_genai_types

logger = logging.getLogger(__name__)


# Per-source content budget when packing the long-context prompt. With ~15
# sources × 8000 chars ≈ 30K tokens of corpus, comfortably inside Gemini's
# context window with room for question + history + tool outputs.
_PER_SOURCE_CHARS = 8000


def _format_corpus(sources: List[Dict]) -> str:
    """Serialize sources into a numbered, citation-friendly block."""
    lines = []
    for index, source in enumerate(sources, start=1):
        title = source.get("title") or source.get("url") or f"Source {index}"
        url = source.get("url") or ""
        summary = (source.get("summary") or "").strip()
        content = (source.get("content") or "").strip()[:_PER_SOURCE_CHARS]
        lines.append(f"[Source {index}] {title}")
        if url:
            lines.append(f"URL: {url}")
        if summary:
            lines.append(f"Summary: {summary}")
        if content:
            lines.append(f"Content:\n{content}")
        lines.append("---")
    return "\n".join(lines)


def _format_history(history: List[Dict], max_turns: int = 6) -> str:
    if not history:
        return "None"
    recent = history[-max_turns:]
    return "\n".join(f"{item.get('role', 'user')}: {item.get('content', '')}" for item in recent)


_SYSTEM_PROMPT = """You are a research assistant chatting about the user's research notebook.

The notebook's sources are listed below as `[Source N]` with title, URL, summary,
and content. Answer the user's question using these sources first.

Rules:
1. Prefer the local sources. Cite them inline as `[Source N]` when you draw on them.
2. If the question requires information not in these sources (e.g. very recent
   events, or a topic outside the corpus), you may use the `google_search` tool.
3. If you need to verify a quote or read a specific passage from a source, you
   may use the `url_context` tool with the source's URL.
4. If you genuinely cannot answer from the sources or tools, say so plainly.
5. Be specific and concrete. Avoid hedging when the sources are clear.
"""


def _extract_cited_source_ids(answer_text: str, sources: List[Dict]) -> List[str]:
    """Find `[Source N]` references in the answer and map back to source IDs.

    Handles every bracket form Gemini emits in practice:

      [Source 1]                       → 1
      [Source 1, 2]                    → 1, 2
      [Source 1, Source 3]             → 1, 3
      [Source 1, 3, 5]                 → 1, 3, 5
      [1, 3, 5]                        → 1, 3, 5  (when the prompt has primed the format)

    Strategy: scan every ``[...]`` bracket in the answer; if the bracket
    text mentions "Source" or contains only numbers and commas, extract
    every digit run inside as a source index. This is far more permissive
    than the previous ``\\[Source\\s+(\\d+)\\]`` regex which silently
    missed everything past the first number in multi-source brackets.
    """
    cited: List[str] = []
    bracket_re = re.compile(r"\[([^\[\]]+)\]")
    digits_only_re = re.compile(r"^[\d\s,]+$")

    for bracket_match in bracket_re.finditer(answer_text):
        inner = bracket_match.group(1)
        # Only treat brackets that look like citation references — either
        # they mention "Source" explicitly, or they're a plain digit-and-
        # commas bracket like ``[1, 3, 5]``.
        is_source_bracket = bool(re.search(r"Source", inner, re.IGNORECASE))
        is_digit_only = bool(digits_only_re.match(inner))
        if not (is_source_bracket or is_digit_only):
            continue
        for num_match in re.finditer(r"\d+", inner):
            try:
                index = int(num_match.group(0)) - 1
            except ValueError:
                continue
            if 0 <= index < len(sources):
                sid = sources[index].get("id")
                if sid and sid not in cited:
                    cited.append(sid)

    # No fallback: if the answer didn't cite anything explicitly, we
    # return an empty list. The UI now interprets an empty cited-set as
    # "clear the graph highlight" — faking citations to keep the array
    # non-empty (which the previous code did) made consecutive questions
    # appear to highlight the same first-3 sources every time, looking
    # frozen.
    return cited


def _fallback_answer(query: str, sources: List[Dict]) -> Dict:
    if not sources:
        return {
            "content": "I do not have any processed sources for this notebook yet. "
                       "Please add a Gemini API key in the header to enable chat.",
            "sources_cited": [],
        }
    bullets = []
    for index, source in enumerate(sources[:3], start=1):
        title = source.get("title") or "Untitled"
        snippet = (source.get("summary") or source.get("content") or "").strip()[:240]
        bullets.append(f"- [Source {index}] {title}: {snippet}")
    return {
        "content": (
            f"(Gemini key not configured — showing extractive preview for: {query})\n\n"
            + "\n".join(bullets)
        ),
        "sources_cited": [s["id"] for s in sources[:3] if s.get("id")],
    }


async def generate_answer(
    query: str,
    sources: List[Dict],
    chat_history: List[Dict],
    *,
    api_key: Optional[str] = None,
) -> Dict:
    """Hybrid grounded answer: long-context corpus + url_context + google_search."""
    client = get_genai_client(api_key)
    types = get_genai_types()
    if client is None or types is None:
        logger.warning("No Gemini client — returning fallback answer")
        return _fallback_answer(query, sources)

    settings = get_settings()
    corpus = _format_corpus(sources)
    history_text = _format_history(chat_history)

    # Tools: url_context (anchored to the notebook's actual URLs) and
    # google_search (for questions that go beyond the corpus).
    tools = []
    try:
        url_list = [s["url"] for s in sources if s.get("url")]
        if hasattr(types, "UrlContext") and url_list:
            tools.append(types.Tool(url_context=types.UrlContext()))
    except Exception as exc:
        logger.warning("url_context tool unavailable, skipping: %s", exc)
    try:
        tools.append(types.Tool(google_search=types.GoogleSearch()))
    except Exception as exc:
        logger.warning("google_search tool unavailable, skipping: %s", exc)

    config_kwargs = {"system_instruction": _SYSTEM_PROMPT}
    if tools:
        config_kwargs["tools"] = tools

    prompt = (
        f"Recent conversation:\n{history_text}\n\n"
        f"Notebook sources:\n{corpus}\n\n"
        f"User question: {query}"
    )

    logger.info(
        "Hybrid chat call: %d sources, %d tools, query=%r",
        len(sources), len(tools), query[:80],
    )
    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )
    except Exception as exc:
        logger.error("Hybrid chat call failed: %s", exc)
        return _fallback_answer(query, sources)

    content = (getattr(response, "text", "") or "").strip()
    if not content:
        logger.warning("Gemini returned empty answer; using fallback")
        return _fallback_answer(query, sources)

    cited_ids = _extract_cited_source_ids(content, sources)
    logger.info("Hybrid answer: %d chars, %d cited sources", len(content), len(cited_ids))
    return {"content": content, "sources_cited": cited_ids}
