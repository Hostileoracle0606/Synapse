import logging
import re
from typing import Dict, List
from urllib.parse import urlparse

from app.config import get_settings

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - import is exercised in integration environments
    genai = None
    types = None

_BLOCKED_DOMAINS = {
    "google.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "reddit.com",
    "youtube.com",
    "linkedin.com",
    "pinterest.com",
    "tiktok.com",
}


def get_gemini_client():
    settings = get_settings()
    if not getattr(settings, "has_gemini", False) or genai is None:
        logger.warning("Gemini client unavailable — discovery will return empty results")
        return None
    return genai.Client(api_key=settings.gemini_api_key)


def _fallback_title(seed_text: str) -> str:
    words = re.findall(r"\w+", seed_text)
    if not words:
        return "Untitled Notebook"
    return " ".join(words[:5]).strip() or "Untitled Notebook"


def _is_valid_source_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname or ""
    # Strip leading "www." for domain matching
    bare = hostname.removeprefix("www.")
    if bare in _BLOCKED_DOMAINS:
        logger.debug("Filtered blocked domain: %s", hostname)
        return False

    # Reject search-query pages
    full = parsed.path + ("?" + parsed.query if parsed.query else "")
    if "?q=" in full or "/search?" in full:
        logger.debug("Filtered search-query URL: %s", url)
        return False

    return True


def _extract_sources_from_response(response, max_results: int) -> List[Dict[str, str]]:
    sources = []
    seen_urls = set()
    skipped = 0
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        metadata = getattr(candidate, "grounding_metadata", None)
        if not metadata:
            continue
        for chunk in getattr(metadata, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)
            url = getattr(web, "uri", None)
            if not url or url in seen_urls:
                continue
            if not _is_valid_source_url(url):
                skipped += 1
                continue
            seen_urls.add(url)
            sources.append(
                {
                    "url": url,
                    "title": getattr(web, "title", None) or url,
                }
            )
            if len(sources) >= max_results:
                break

    logger.info("Extracted %d sources from Gemini response (%d filtered out)", len(sources), skipped)
    return sources


async def discover_related_sources(seed_text: str, max_results: int = 15) -> List[Dict[str, str]]:
    logger.info("Starting discovery (max_results=%d, seed_length=%d chars)", max_results, len(seed_text))
    client = get_gemini_client()
    if client is None or types is None:
        logger.warning("Discovery skipped — no Gemini client")
        return []

    settings = get_settings()
    prompt = (
        "Based on the following text, find related and authoritative sources on the web "
        "that cover the same topics, provide additional context, or offer different "
        "perspectives. Return diverse source types: research papers, news articles, "
        "technical blogs, official documentation, and reports.\n\n"
        "TEXT:\n"
        f"{seed_text[:4000]}\n\n"
        f"Find {max_results} highly relevant sources."
    )

    logger.info("Calling Gemini (%s) with Google Search grounding for discovery", settings.gemini_model)
    response = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )
    sources = _extract_sources_from_response(response, max_results)
    logger.info("Discovery complete — found %d source(s)", len(sources))
    for i, s in enumerate(sources, 1):
        logger.info("  [%d] %s — %s", i, s.get("title", ""), s.get("url", ""))
    return sources


async def extract_seed_title(seed_text: str) -> str:
    logger.info("Extracting title from seed text (%d chars)", len(seed_text))
    client = get_gemini_client()
    if client is None:
        title = _fallback_title(seed_text)
        logger.info("Using fallback title: %s", title)
        return title

    settings = get_settings()
    response = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=(
            "Generate a short title, five words or fewer, for a research notebook about "
            "the following text. Return only the title.\n\n"
            f"{seed_text[:2000]}"
        ),
    )
    text = (getattr(response, "text", "") or "").strip().strip('"')
    title = text or _fallback_title(seed_text)
    logger.info("Extracted title: %s", title)
    return title
