import json
import logging
import math
import time
from typing import Dict, List, Optional

from app.config import get_settings

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


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(left * right for left, right in zip(a, b))
    norm_a = math.sqrt(sum(value * value for value in a))
    norm_b = math.sqrt(sum(value * value for value in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def normalize_vector(values: List[float]) -> List[float]:
    if not values:
        return []
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        return [0.0 for _ in values]
    return [value / norm for value in values]


def centroid_from_chunk_embeddings(chunk_embeddings: List[List[float]]) -> List[float]:
    if not chunk_embeddings:
        return []

    normalized_chunks = [normalize_vector(chunk) for chunk in chunk_embeddings if chunk]
    if not normalized_chunks:
        return []

    width = len(normalized_chunks[0])
    total = len(normalized_chunks)
    skipped = 0
    centroid = [0.0] * width
    counted = 0
    for embedding in normalized_chunks:
        if len(embedding) != width:
            skipped += 1
            continue
        counted += 1
        for index, value in enumerate(embedding):
            centroid[index] += value

    if skipped > 0:
        if skipped / total > 0.10:
            raise ValueError(
                f"Data corruption: {skipped}/{total} chunk embeddings have wrong dimensions"
            )
        logger.warning(
            "%d/%d chunk embeddings had wrong dimensions and were skipped", skipped, total
        )

    if counted == 0:
        return []
    centroid = [value / counted for value in centroid]
    return normalize_vector(centroid)


def _coerce_embedding(raw) -> list[float]:
    """Return a list[float] regardless of whether Supabase returned a string or a list.

    PostgREST serialises pgvector columns as a plain text string, e.g.
    ``"[0.003,0.020,-0.005,...]"``.  When the in-memory backend is used (or a
    future PostgREST version that natively serialises vectors as JSON arrays)
    the value may already be a Python list.
    """
    if isinstance(raw, list):
        return [float(v) for v in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [float(v) for v in parsed]
        except (json.JSONDecodeError, ValueError, TypeError):
            logger.warning("Failed to parse embedding string (len=%d)", len(raw))
    return []


def source_centroids_from_chunks(sources: List[Dict], chunks: List[Dict]) -> List[Dict]:
    chunk_embeddings_by_source: dict[str, list[list[float]]] = {}
    for chunk in chunks:
        emb = _coerce_embedding(chunk.get("embedding"))
        if emb:
            chunk_embeddings_by_source.setdefault(chunk["source_id"], []).append(emb)

    centroids = []
    for source in sources:
        embedding = centroid_from_chunk_embeddings(chunk_embeddings_by_source.get(source["id"], []))
        if not embedding:
            continue
        centroids.append(
            {
                "id": source["id"],
                "title": source.get("title"),
                "summary": source.get("summary"),
                "embedding": embedding,
            }
        )
    return centroids


def compute_edges(docs: List[Dict], chunks: Optional[List[Dict]] = None, threshold: float = 0.4) -> List[Dict]:
    if chunks is not None:
        docs = source_centroids_from_chunks(docs, chunks)

    logger.info("Computing edges for %d documents (threshold=%.2f)", len(docs), threshold)
    t0 = time.monotonic()
    edges = []
    total_pairs = 0
    for index, doc in enumerate(docs):
        for other in docs[index + 1 :]:
            total_pairs += 1
            similarity = cosine_similarity(doc.get("embedding", []), other.get("embedding", []))
            if similarity >= threshold:
                edges.append(
                    {
                        "source_a": doc["id"],
                        "source_b": other["id"],
                        "similarity": round(similarity, 4),
                    }
                )
                logger.debug(
                    "Edge: %r <-> %r  sim=%.4f",
                    doc.get("title", doc["id"]),
                    other.get("title", other["id"]),
                    similarity,
                )

    logger.info(
        "Edge computation done in %.1fs - %d/%d pairs exceed threshold",
        time.monotonic() - t0, len(edges), total_pairs,
    )
    return edges


async def generate_edge_labels(edges: List[Dict], docs_by_id: Dict[str, Dict]) -> List[Dict]:
    if not edges:
        logger.info("No edges to label")
        return edges

    client = get_gemini_client()
    if client is None:
        logger.warning("No Gemini client - using default label 'related topics' for all edges")
        for edge in edges:
            edge["relationship"] = "related topics"
        return edges

    settings = get_settings()
    batch_size = getattr(get_settings(), "edge_label_batch_size", 20)
    logger.info("Generating labels for %d edges in batches of %d", len(edges), batch_size)

    for batch_start in range(0, len(edges), batch_size):
        batch = edges[batch_start : batch_start + batch_size]
        logger.info("Labeling batch %d-%d of %d", batch_start + 1, batch_start + len(batch), len(edges))
        descriptions = []
        for edge in batch:
            left = docs_by_id.get(edge["source_a"], {})
            right = docs_by_id.get(edge["source_b"], {})
            descriptions.append(
                '- "{left_title}" (summary: {left_summary}) <-> "{right_title}" (summary: {right_summary})'.format(
                    left_title=left.get("title", "?"),
                    left_summary=(left.get("summary") or "N/A")[:200],
                    right_title=right.get("title", "?"),
                    right_summary=(right.get("summary") or "N/A")[:200],
                )
            )

        prompt = (
            "For each pair of documents below, write a short phrase under ten words "
            "explaining how they are related. Return one line per pair in the same order.\n\n"
            + "\n".join(descriptions)
        )
        response = await client.aio.models.generate_content(model=settings.gemini_model, contents=prompt)
        raw_labels = [line.strip() for line in (getattr(response, "text", "") or "").splitlines() if line.strip()]

        if not isinstance(raw_labels, list):
            raw_labels = []

        logger.info("Got %d labels from Gemini for batch of %d edges", len(raw_labels), len(batch))
        for index, edge in enumerate(batch):
            edge["relationship"] = raw_labels[index] if index < len(raw_labels) else "related topics"
            logger.debug(
                "Label: %r <-> %r = %r",
                docs_by_id.get(edge["source_a"], {}).get("title", edge["source_a"]),
                docs_by_id.get(edge["source_b"], {}).get("title", edge["source_b"]),
                edge["relationship"],
            )

    return edges
