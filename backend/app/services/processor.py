from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
import time
from typing import List

from app.config import get_settings
from app.services.chunking import chunk_text

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover - import is exercised in integration environments
    genai = None
    genai_types = None


def get_gemini_client():
    settings = get_settings()
    if not settings.gemini_api_key or genai is None:
        return None
    return genai.Client(api_key=settings.gemini_api_key)


def _fallback_summary(text: str, title: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    selected = " ".join(sentence for sentence in sentences[:2] if sentence).strip()
    if selected:
        return selected[:600]
    return (title or "Document") + ": " + text[:240].strip()


def _embedding_dimension() -> int:
    settings = get_settings()
    if settings.embedding_dimension <= 0:
        raise ValueError("embedding_dimension must be a positive integer")
    return settings.embedding_dimension


def _fallback_embedding(text: str) -> List[float]:
    dimension = _embedding_dimension()
    vector = [0.0] * dimension
    tokens = re.findall(r"\w+", text.lower())
    if not tokens:
        return vector

    for token in tokens[:2000]:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        slot = int.from_bytes(digest[:2], "big") % dimension
        value = 0.5 + (digest[2] / 255.0)
        vector[slot] += value

    norm = math.sqrt(sum(item * item for item in vector))
    if norm == 0:
        return vector
    return [item / norm for item in vector]


async def summarize_document(text: str, title: str) -> str:
    client = get_gemini_client()
    if client is None:
        logger.warning("No Gemini client — using fallback summary for %r", title)
        return _fallback_summary(text, title)

    settings = get_settings()
    logger.info("Summarizing %r (%d chars)", title, len(text))
    t0 = time.monotonic()
    response = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=(
            "Summarize this document in 2-3 sentences. Be specific about the key claims "
            "and findings.\n\n"
            f"Title: {title}\n\n{text[:6000]}"
        ),
    )
    summary = (getattr(response, "text", "") or "").strip() or _fallback_summary(text, title)
    logger.info("Summary done (%.1fs) for %r — %d chars", time.monotonic() - t0, title, len(summary))
    return summary


async def embed_document(text: str) -> List[float]:
    client = get_gemini_client()
    if client is None:
        logger.warning("No Gemini client — using fallback embedding")
        return _fallback_embedding(text)

    settings = get_settings()
    truncated = text[:8000]

    embed_config = None
    if genai_types is not None:
        embed_config = genai_types.EmbedContentConfig(
            task_type="SEMANTIC_SIMILARITY",
            output_dimensionality=settings.embedding_dimension,
        )

    result = await client.aio.models.embed_content(
        model=settings.gemini_embed_model,
        contents=truncated,
        config=embed_config,
    )
    values = [float(item) for item in result.embeddings[0].values]
    logger.debug("Embedding produced dim=%d for %d input chars", len(values), len(truncated))
    return values


async def embed_chunks(text: str, max_concurrent: int = 5) -> list[dict]:
    """Embed all chunks from *text* with bounded concurrency."""
    chunks = chunk_text(text)
    if not chunks:
        logger.warning("No chunks produced from text of %d chars", len(text))
        return []

    logger.info("Embedding %d chunks (max_concurrent=%d)", len(chunks), max_concurrent)
    sem = asyncio.Semaphore(max_concurrent)
    expected_dim = _embedding_dimension()

    async def _embed_one(chunk: dict) -> dict | None:
        async with sem:
            embedding = await embed_document(chunk["content"])
            if not embedding:
                logger.warning("Empty embedding for chunk %d", chunk.get("chunk_index", "?"))
                return None
            if len(embedding) != expected_dim:
                logger.warning(
                    "Chunk %d embedding dim=%d (expected %d) — skipping",
                    chunk.get("chunk_index", "?"),
                    len(embedding),
                    expected_dim,
                )
                return None
            return {**chunk, "embedding": embedding}

    results = await asyncio.gather(
        *[_embed_one(c) for c in chunks],
        return_exceptions=True,
    )

    stored_chunks = []
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Chunk embedding failed: %s", result)
            continue
        if result is not None:
            stored_chunks.append(result)

    logger.info("Embedded %d/%d chunks successfully", len(stored_chunks), len(chunks))
    return stored_chunks
