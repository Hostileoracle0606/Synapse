from __future__ import annotations

import logging
import re
import time
from typing import Optional

from app.config import get_settings
from app.services._gemini import get_genai_client

logger = logging.getLogger(__name__)


def _fallback_summary(text: str, title: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    selected = " ".join(sentence for sentence in sentences[:2] if sentence).strip()
    if selected:
        return selected[:600]
    return (title or "Document") + ": " + text[:240].strip()


async def summarize_document(text: str, title: str, *, api_key: Optional[str] = None) -> str:
    """Summarize a document with Gemini, falling back to extractive on failure.

    BYOK: pass `api_key` to use a per-request key; otherwise falls back to env.
    """
    client = get_genai_client(api_key)
    if client is None:
        logger.warning("No Gemini client — using fallback summary for %r", title)
        return _fallback_summary(text, title)

    settings = get_settings()
    logger.info("Summarizing %r (%d chars)", title, len(text))
    t0 = time.monotonic()
    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=(
                "Summarize this document in 2-3 sentences. Be specific about the key claims "
                "and findings.\n\n"
                f"Title: {title}\n\n{text[:6000]}"
            ),
        )
        summary = (getattr(response, "text", "") or "").strip() or _fallback_summary(text, title)
    except Exception as exc:
        logger.warning("Summary call failed for %r — using fallback: %s", title, exc)
        summary = _fallback_summary(text, title)
    logger.info("Summary done (%.1fs) for %r — %d chars", time.monotonic() - t0, title, len(summary))
    return summary
