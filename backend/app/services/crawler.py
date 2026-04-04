from __future__ import annotations

import asyncio
import json
import logging
from html.parser import HTMLParser
from typing import Any

import httpx

from app.config import get_settings

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


async def smart_crawl_url(url: str, source_type: str = "webpage") -> dict[str, str] | None:
    """Route *url* to the best extractor and always return success dict or None.

    PDF routing (either explicit source_type or .pdf extension):
        Firecrawl first → None on failure (no httpx fallback)

    Webpage routing:
        httpx+trafilatura first → Firecrawl fallback on None/error/weak text
        If Firecrawl also unavailable/fails → return weak primary if text >= threshold;
        otherwise None
    """
    settings = get_settings()

    if _looks_like_pdf(url, source_type):
        return await crawl_url_with_firecrawl(url)

    # Primary: httpx + trafilatura
    primary = await crawl_url(url)

    # Determine whether primary is good enough
    primary_text = (primary or {}).get("text", "") if primary and not primary.get("error") else ""
    primary_is_weak = len(primary_text.strip()) < settings.firecrawl_fallback_min_chars

    if not primary_is_weak:
        # Strip error keys — return clean success dict only
        return {"text": primary_text, "title": (primary or {}).get("title") or url}

    # Try Firecrawl fallback
    fc_result = await crawl_url_with_firecrawl(url)
    if fc_result:
        return fc_result

    # Firecrawl unavailable or failed — return weak primary if it has usable text
    if primary_text:
        return {"text": primary_text, "title": (primary or {}).get("title") or url}

    return None


def _extract_title_from_metadata(html: str) -> str:
    if trafilatura is None:
        return ""

    metadata = trafilatura.extract(html, output_format="json", include_comments=False)
    if not metadata:
        return ""

    try:
        parsed = json.loads(metadata)
    except json.JSONDecodeError:
        return ""
    return parsed.get("title") or ""


def _fallback_result(url: str, html: str) -> dict[str, str]:
    """Strip HTML and return plain text, or a structured failure if too short."""
    settings = get_settings()
    text = _strip_html(html)
    if len(text) < 50:
        return _failure_result(url)
    return {
        "title": url,
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


async def crawl_url(url: str, timeout: float = 15.0) -> dict[str, str] | None:
    settings = get_settings()
    logger.info("Crawling: %s", url)
    client_kwargs = dict(
        timeout=timeout,
        follow_redirects=True,
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
    title = _extract_title_from_metadata(html) or url
    logger.info("Crawl OK - %d chars, title=%r: %s", len(truncated), title, url)
    return {"text": truncated, "title": title}
