from __future__ import annotations

import asyncio
import json
import logging
import re
import ssl
from html.parser import HTMLParser
from typing import Any, Optional

import certifi
import httpx

from app.config import get_settings


# Build a single SSL context backed by certifi's CA bundle. Without this,
# httpx falls back to Python's default trust store, which on Homebrew Python
# doesn't always resolve a usable path → "unable to get local issuer
# certificate" errors when crawling sites with chains like Let's Encrypt.
_SSL_CTX = ssl.create_default_context(cafile=certifi.where())

logger = logging.getLogger(__name__)

try:
    import trafilatura
except Exception:  # pragma: no cover - optional dependency
    trafilatura = None  # type: ignore[assignment]

try:
    from firecrawl import AsyncFirecrawlApp
except Exception:  # pragma: no cover - optional dependency
    AsyncFirecrawlApp = None  # type: ignore[assignment,misc]

# Content-Type prefixes/values that indicate non-text binary content.
_SKIP_CONTENT_TYPE_PREFIXES = ("image/", "audio/", "video/")
_SKIP_CONTENT_TYPE_EXACT = {
    "application/pdf",
    "application/zip",
    "application/octet-stream",
}

# Content-Type values that are safe to fetch and parse.
_VALID_CONTENT_TYPE_PREFIXES = (
    "text/html",
    "text/plain",
    "application/json",
    "application/xhtml+xml",
)


class _TextStripper(HTMLParser):
    """Collect visible text from HTML, skipping <script> and <style> blocks."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth: int = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts).strip()


def _strip_html(html: str) -> str:
    """Return plain text extracted from *html*, with whitespace normalised."""
    stripper = _TextStripper()
    stripper.feed(html)
    # Collapse runs of whitespace (spaces, newlines, tabs) to single spaces.
    import re
    return re.sub(r"\s+", " ", stripper.get_text()).strip()


def _failure_result(url: str) -> dict[str, str]:
    return {"url": url, "title": "", "content": "", "error": "Content extraction failed"}


def _looks_like_pdf(url: str, source_type: str) -> bool:
    """Return True when the URL or explicit source_type indicates a PDF."""
    return source_type == "pdf" or url.lower().split("?")[0].endswith(".pdf")


async def crawl_url_with_firecrawl(url: str, timeout: float = 30.0) -> dict[str, str] | None:
    """Fetch *url* via the Firecrawl API and return {"text": ..., "title": ...}.

    Returns None if Firecrawl is unavailable, the key is unset, the result is
    empty, times out, or any exception is raised.
    """
    settings = get_settings()
    if AsyncFirecrawlApp is None or not settings.firecrawl_api_key:
        return None
    try:
        app = AsyncFirecrawlApp(api_key=settings.firecrawl_api_key)
        result = await asyncio.wait_for(
            app.scrape(url, formats=["markdown"]),
            timeout=timeout,
        )
        markdown = getattr(result, "markdown", None)
        if not markdown:
            return None
        metadata = getattr(result, "metadata", None)
        title = (getattr(metadata, "title", None) if metadata else None) or url
        return {"text": markdown[: settings.max_document_chars], "title": title}
    except asyncio.TimeoutError:
        logger.warning("Firecrawl timed out (%.0fs) for %s", timeout, url)
        return None
    except Exception as exc:
        logger.warning("Firecrawl failed for %s: %s", url, exc)
        return None


async def _resolve_final_url_and_type(url: str, timeout: float = 8.0) -> tuple[str, str]:
    """HEAD-probe *url*, follow redirects, return (final_url, content_type).

    Critical for Gemini-discovered URLs which arrive wrapped in
    ``vertexaisearch.cloud.google.com/grounding-api-redirect/...`` — the
    routing decision (HTML vs PDF vs YouTube) needs the post-redirect
    target, not the wrapper.
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=_SSL_CTX,
            headers={"User-Agent": "Synapse-Bot/1.0 (research tool)"},
        ) as client:
            response = await client.head(url)
            final = str(response.url)
            ct = response.headers.get("content-type", "").split(";")[0].strip().lower()
            return final, ct
    except Exception as exc:
        logger.debug("HEAD probe failed for %s (%s) — using URL as-is", url, exc)
        return url, ""


async def smart_crawl_url(
    url: str,
    source_type: str = "webpage",
    *,
    api_key: Optional[str] = None,
) -> dict[str, str] | None:
    """Route *url* to the right extractor based on the actual content type.

    Decision tree (after resolving redirects):

    - YouTube URL  → Gemini native video ingest (transcribes the video)
    - PDF (URL extension OR Content-Type: application/pdf) →
        Gemini native PDF parse → Firecrawl fallback on failure
    - Other binary (image/audio/video/zip/octet-stream) → bail (no parser)
    - HTML/text → trafilatura primary → Firecrawl fallback on weak text

    BYOK: ``api_key`` flows into the Gemini-native ingesters. HTML path
    doesn't need it.
    """
    settings = get_settings()

    # Local import: gemini_ingest imports _SSL_CTX from this module, so we
    # defer the import to avoid a circular-import at module load time.
    from app.services.gemini_ingest import (
        gemini_ingest_pdf,
        gemini_ingest_via_tools,
        gemini_ingest_youtube,
        is_tools_fallback_url,
        is_youtube_url,
    )

    # ── Resolve redirects to discover the actual destination ───────────────
    # Gemini grounding wraps every URL in a vertexaisearch redirect, so the
    # input ``url`` rarely tells us the true type. The HEAD probe also gives
    # us the server-reported Content-Type for free.
    final_url, final_ct = await _resolve_final_url_and_type(url)

    # Helper: tag every successful return with the resolved URL so the
    # worker can write it back onto the source record (replacing the original
    # vertexaisearch redirect wrapper). This is what makes URL-based dedup
    # actually work post-crawl.
    def _tag(result, source_type):
        if result is None:
            return None
        result.setdefault("source_type", source_type)
        result.setdefault("final_url", final_url or url)
        return result

    # ── YouTube → native Gemini video ingest ───────────────────────────────
    # We tried routing YouTube through gemini_ingest_via_tools (url_context
    # + google_search) in an earlier iteration; Gemini's url_context tool
    # explicitly refuses YouTube URLs (returns NOT_ACCESSIBLE). The video
    # file_uri path remains the only Gemini-native way to get transcripts.
    if is_youtube_url(final_url) or is_youtube_url(url):
        return _tag(await gemini_ingest_youtube(final_url, api_key=api_key), "youtube")

    # ── PDF (extension OR resolved content-type) → native Gemini PDF parse ─
    is_pdf = (
        _looks_like_pdf(url, source_type)
        or _looks_like_pdf(final_url, source_type)
        or final_ct == "application/pdf"
    )
    if is_pdf:
        gemini_pdf = await gemini_ingest_pdf(final_url or url, api_key=api_key)
        if gemini_pdf:
            return _tag(gemini_pdf, "pdf")
        return _tag(await crawl_url_with_firecrawl(final_url or url), "pdf")

    # ── Tools-fallback domains (Twitter/X, Reddit, LinkedIn, Threads) ──────
    if is_tools_fallback_url(final_url) or is_tools_fallback_url(url):
        return _tag(
            await gemini_ingest_via_tools(final_url or url, api_key=api_key),
            "social",
        )

    # ── Other binary content → no parser, bail early ────────────────────────
    if final_ct and _content_type_is_binary(final_ct):
        logger.warning("Skipping unsupported binary content (%s): %s", final_ct, final_url)
        return None

    # ── HTML / text path: trafilatura primary, Firecrawl fallback ──────────
    primary = await crawl_url(url)

    primary_text = (primary or {}).get("text", "") if primary and not primary.get("error") else ""
    primary_is_weak = len(primary_text.strip()) < settings.firecrawl_fallback_min_chars

    if not primary_is_weak:
        return _tag(
            {
                "text": primary_text,
                "title": (primary or {}).get("title") or _hostname_label(final_url or url),
            },
            "webpage",
        )

    fc_result = await crawl_url_with_firecrawl(url)
    if fc_result:
        if not fc_result.get("title") or fc_result["title"].lower().startswith(("http://", "https://")):
            fc_result["title"] = _hostname_label(final_url or url)
        return _tag(fc_result, "webpage")

    if primary_text:
        return _tag(
            {
                "text": primary_text,
                "title": (primary or {}).get("title") or _hostname_label(final_url or url),
            },
            "webpage",
        )

    # ── Last-resort: tools-based ingest ────────────────────────────────────
    logger.info("All cheap extractors failed; trying tools-based fallback for %s", url)
    return _tag(
        await gemini_ingest_via_tools(final_url or url, api_key=api_key),
        "webpage",
    )


_TITLE_TAG_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE | re.DOTALL)
_OG_TITLE_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_TITLE_NOISE_SUFFIXES = (
    " - Wikipedia",
    " | Wikipedia",
    " - GitHub",
    " - YouTube",
)


def _clean_title(raw: str) -> str:
    """Strip tags, collapse whitespace, drop common site-name suffixes."""
    if not raw:
        return ""
    text = _TAG_STRIP_RE.sub("", raw)
    text = _WS_RE.sub(" ", text).strip()
    if not text:
        return ""
    # Drop boilerplate suffixes — keeps "Attention Is All You Need" not
    # "Attention Is All You Need - arxiv.org" etc.
    for suffix in _TITLE_NOISE_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text[:200]


def _extract_title_from_metadata(html: str) -> str:
    """Best-effort title extraction with no LLM cost.

    Tries in order:
    1. ``<meta property="og:title">``  (most reliable for news/articles)
    2. ``<title>`` tag                (universal fallback)
    3. trafilatura's article-content title (works on blog-shaped pages)
    4. The first ``<h1>`` (last resort for sparse pages)
    """
    # 1. og:title
    m = _OG_TITLE_RE.search(html)
    if m:
        cleaned = _clean_title(m.group(1))
        if cleaned and not cleaned.lower().startswith(("http://", "https://")):
            return cleaned

    # 2. <title> tag — typically wraps the page title
    m = _TITLE_TAG_RE.search(html)
    if m:
        cleaned = _clean_title(m.group(1))
        if cleaned and not cleaned.lower().startswith(("http://", "https://")):
            return cleaned

    # 3. trafilatura's article-title (only useful if it actually returns one;
    # often empty on landing pages and search-result pages)
    if trafilatura is not None:
        try:
            metadata = trafilatura.extract(html, output_format="json", include_comments=False)
            if metadata:
                parsed = json.loads(metadata)
                cleaned = _clean_title(parsed.get("title") or "")
                if cleaned:
                    return cleaned
        except (json.JSONDecodeError, Exception):
            pass

    # 4. First <h1>
    m = _H1_RE.search(html)
    if m:
        cleaned = _clean_title(m.group(1))
        if cleaned:
            return cleaned

    return ""


def _hostname_label(url: str) -> str:
    """Friendly hostname-based label for fallback titles."""
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
        return host.removeprefix("www.") if host else url
    except Exception:
        return url


def _fallback_result(url: str, html: str) -> dict[str, str]:
    """Strip HTML and return plain text, or a structured failure if too short."""
    settings = get_settings()
    text = _strip_html(html)
    if len(text) < 50:
        return _failure_result(url)
    return {
        # Try to recover a real title from the HTML even on the fallback path
        # (trafilatura returned weak text — that doesn't mean the <title>
        # tag is missing). Hostname is the last-resort label.
        "title": _extract_title_from_metadata(html) or _hostname_label(url),
        "text": text[: settings.max_document_chars],
    }


def _content_type_is_binary(content_type: str) -> bool:
    """Return True when the Content-Type indicates a non-text binary resource."""
    ct = content_type.split(";")[0].strip().lower()
    if ct in _SKIP_CONTENT_TYPE_EXACT:
        return True
    return any(ct.startswith(prefix) for prefix in _SKIP_CONTENT_TYPE_PREFIXES)


def _content_type_is_valid(content_type: str) -> bool:
    """Return True when the Content-Type is a known text/parseable format."""
    ct = content_type.split(";")[0].strip().lower()
    return any(ct.startswith(prefix) for prefix in _VALID_CONTENT_TYPE_PREFIXES)


async def crawl_url(url: str, timeout: float = 30.0) -> dict[str, str] | None:
    settings = get_settings()
    logger.info("Crawling: %s", url)
    client_kwargs = dict(
        timeout=timeout,
        follow_redirects=True,
        verify=_SSL_CTX,
        headers={"User-Agent": "Synapse-Bot/1.0 (research tool)"},
    )

    async with httpx.AsyncClient(**client_kwargs) as client:
        # Content-Type guard via HEAD request
        try:
            head_response = await client.head(url)
            content_type = head_response.headers.get("content-type", "")
            if content_type and _content_type_is_binary(content_type):
                logger.warning("Skipping binary content (%s): %s", content_type, url)
                return _failure_result(url)
            logger.debug("HEAD ok - content-type: %s  url: %s", content_type or "(none)", url)
        except Exception as exc:
            logger.debug("HEAD failed (%s), proceeding with GET: %s", exc, url)

        # Full body fetch
        try:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text
            logger.debug("GET %d - %d chars received: %s", response.status_code, len(html), url)
        except httpx.TimeoutException:
            logger.warning("Timeout fetching: %s", url)
            return None
        except httpx.HTTPError as exc:
            logger.warning("HTTP error fetching %s: %s", url, exc)
            return None

    if trafilatura is None:
        result = _fallback_result(url, html)
        logger.info("Fallback extraction - %d chars: %s", len(result.get("text", "")), url)
        return result

    text = trafilatura.extract(html, include_comments=False, include_tables=True)
    if not text or len(text) < 50:
        logger.warning("Trafilatura insufficient text (%d chars), using fallback: %s", len(text or ""), url)
        return _fallback_result(url, html)

    truncated = text[: settings.max_document_chars]
    # Title preference: rich metadata → og:title/title tag/h1 → cleaned hostname.
    # Never return the raw URL as the title; it makes the sidebar unreadable.
    title = _extract_title_from_metadata(html) or _hostname_label(url)
    logger.info("Crawl OK - %d chars, title=%r: %s", len(truncated), title, url)
    return {"text": truncated, "title": title}
