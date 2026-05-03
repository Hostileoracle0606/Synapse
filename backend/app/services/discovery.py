import asyncio
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import urlparse

from app.config import get_settings
from app.services._gemini import get_genai_client, get_genai_types

logger = logging.getLogger(__name__)

_BLOCKED_DOMAINS = {
    "google.com",
    # twitter.com / x.com / reddit.com / linkedin.com — now allowed:
    # gemini_ingest.gemini_ingest_via_tools fetches them through Gemini's
    # url_context + google_search tools.
    # youtube.com — now allowed: gemini_ingest_youtube parses videos
    # natively at crawl time.
    "facebook.com",
    "instagram.com",
    "pinterest.com",
    "tiktok.com",
}


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
    bare = hostname.removeprefix("www.")
    if bare in _BLOCKED_DOMAINS:
        logger.debug("Filtered blocked domain: %s", hostname)
        return False

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


def _split_quota(total: int) -> Dict[str, int]:
    """Split the discovery budget across the three type-scoped calls.

    The split favours articles (the most plentiful + reliable) while still
    guaranteeing at least one paper and one video slot for any total >= 4.
    For very small totals we collapse missing slots into articles so we
    never make a wasted call.
    """
    total = max(0, total)
    if total <= 0:
        return {"articles": 0, "papers": 0, "videos": 0}
    if total <= 2:
        return {"articles": total, "papers": 0, "videos": 0}
    if total <= 4:
        # 3→ 2/1/0  4→ 2/1/1
        return {
            "articles": total - (1 + (1 if total >= 4 else 0)),
            "papers": 1,
            "videos": 1 if total >= 4 else 0,
        }
    # 5+ : roughly 50% articles, 25% papers, 25% videos
    papers = max(1, total // 4)
    videos = max(1, total // 4)
    articles = total - papers - videos
    return {"articles": articles, "papers": papers, "videos": videos}


_TYPE_PROMPTS = {
    "articles": (
        "Find up to {n} authoritative web articles, news pieces, or "
        "technical blog posts that are highly relevant to the topic. Prefer "
        "primary sources, recognised publications, and detailed write-ups. "
        "Avoid forums, search-result pages, and low-quality SEO content."
    ),
    "papers": (
        "Find up to {n} academic papers, research preprints, technical "
        "reports, or white papers that are highly relevant to the topic. "
        "Prefer arXiv, NeurIPS, ACL, and similar peer-reviewed or "
        "preprint repositories. PDFs are acceptable. If no high-quality "
        "papers exist, return fewer."
    ),
    "videos": (
        "Find up to {n} high-quality YouTube videos — lectures, conference "
        "talks, technical explainers — that are highly relevant to the "
        "topic. Prefer videos from recognised researchers, university "
        "channels, or technical-conference accounts. If no strong videos "
        "exist, return fewer."
    ),
}


async def _discover_for_type(
    *,
    type_key: str,
    quota: int,
    seed_text: str,
    api_key: Optional[str],
) -> List[Dict[str, str]]:
    """Run a single type-scoped grounded discovery call. Used by the
    fan-out in ``discover_related_sources``."""
    if quota <= 0:
        return []
    client = get_genai_client(api_key)
    types = get_genai_types()
    if client is None or types is None:
        return []

    settings = get_settings()
    type_directive = _TYPE_PROMPTS[type_key].format(n=quota)
    prompt = (
        f"{type_directive}\n\n"
        "TEXT:\n"
        f"{seed_text[:4000]}"
    )
    logger.info(
        "Discovery [%s]: requesting up to %d sources (model=%s)",
        type_key, quota, settings.gemini_model,
    )
    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
        )
    except Exception as exc:
        logger.warning("Discovery [%s] failed: %s", type_key, exc)
        return []
    sources = _extract_sources_from_response(response, quota)
    logger.info("Discovery [%s]: %d sources", type_key, len(sources))
    return sources


async def discover_related_sources(
    seed_text: str,
    max_results: int = 15,
    *,
    api_key: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Discover related sources with guaranteed type diversity.

    Fans out the discovery into three parallel grounded calls (articles,
    papers, videos), each scoped via the prompt to surface its own type.
    Combines the results and de-dupes by URL. Cost: 3× the LLM calls of a
    single-shot discovery, but they run in parallel so wall-clock is the
    same as today's single discovery call. Quality: guaranteed mix of
    types instead of Gemini's default web-article-heavy bias.
    """
    logger.info("Starting discovery (max_results=%d, seed_length=%d chars)", max_results, len(seed_text))
    client = get_genai_client(api_key)
    types_mod = get_genai_types()
    if client is None or types_mod is None:
        logger.warning("Discovery skipped — no Gemini client (BYOK key missing or SDK unavailable)")
        return []

    quotas = _split_quota(max_results)
    logger.info("Discovery quotas: %s", quotas)

    type_results = await asyncio.gather(
        *[
            _discover_for_type(
                type_key=key,
                quota=quotas[key],
                seed_text=seed_text,
                api_key=api_key,
            )
            for key in ("articles", "papers", "videos")
        ],
        return_exceptions=True,
    )

    # Merge results in the order articles → papers → videos so the seed
    # surface naturally feels mixed when streamed into the UI.
    seen_urls: set[str] = set()
    merged: List[Dict[str, str]] = []
    breakdown = {"articles": 0, "papers": 0, "videos": 0}
    for type_key, result in zip(("articles", "papers", "videos"), type_results):
        if isinstance(result, Exception):
            logger.warning("Discovery [%s] raised: %s", type_key, result)
            continue
        for item in (result or []):
            url = (item or {}).get("url") or ""
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            merged.append(item)
            breakdown[type_key] += 1

    logger.info(
        "Discovery complete — %d sources total (articles=%d, papers=%d, videos=%d)",
        len(merged), breakdown["articles"], breakdown["papers"], breakdown["videos"],
    )
    for i, s in enumerate(merged, 1):
        logger.info("  [%d] %s — %s", i, s.get("title", ""), s.get("url", ""))
    return merged[:max_results]


async def extract_seed_title(seed_text: str, *, api_key: Optional[str] = None) -> str:
    """Title extraction now prefers the cheap fallback to save an LLM call.

    Kept around so the existing routers contract still works, but no longer
    calls Gemini — first 5 words is good enough for a notebook title.
    """
    title = _fallback_title(seed_text)
    logger.info("Title (extractive, no LLM): %s", title)
    return title
