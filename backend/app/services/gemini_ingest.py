"""Native Gemini multi-modal ingest for non-HTML source types.

trafilatura handles webpages well and cheaply, but it can't read PDFs or
videos. This module hands those to Gemini, which has native parsers for:

- PDFs: downloaded as bytes, then sent inline to generate_content
- YouTube videos: passed by URL — Gemini watches/transcribes natively

Each function returns the same shape as crawl_url (`{"text", "title"}`)
or None on failure, so the worker pipeline doesn't need to care which
extractor produced the content.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
from urllib.parse import parse_qs, urlparse

import httpx

from app.config import get_settings
from app.services._gemini import get_genai_client, get_genai_types

logger = logging.getLogger(__name__)


_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "music.youtube.com",
}

try:
    from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    YouTubeTranscriptApi = None  # type: ignore[assignment]

# Domains where the "normal" trafilatura path will almost certainly be
# bot-blocked or login-walled. We route these straight to the tools-based
# ingester instead of paying the cost of letting trafilatura fail first.
_TOOLS_FALLBACK_HOSTS = {
    # Twitter / X
    "twitter.com", "www.twitter.com", "mobile.twitter.com",
    "x.com", "www.x.com",
    # Reddit
    "reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com", "np.reddit.com",
    # LinkedIn
    "linkedin.com", "www.linkedin.com",
    # Threads (Meta's Twitter alternative — also bot-walled)
    "threads.net", "www.threads.net",
}


def is_youtube_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in _YOUTUBE_HOSTS


def is_tools_fallback_url(url: str) -> bool:
    """Return True for domains where tools-based ingest is the right first try."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in _TOOLS_FALLBACK_HOSTS


def _normalize_youtube_url(url: str) -> str:
    """Convert various YouTube URL forms to the canonical watch URL."""
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        video_id = parsed.path.lstrip("/")
        return f"https://www.youtube.com/watch?v={video_id}" if video_id else url
    if host in _YOUTUBE_HOSTS:
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            video_id = (qs.get("v") or [""])[0]
            if video_id:
                return f"https://www.youtube.com/watch?v={video_id}"
        if parsed.path.startswith("/shorts/"):
            parts = parsed.path.split("/", 2)
            if len(parts) >= 3 and parts[2]:
                return f"https://www.youtube.com/watch?v={parts[2]}"
    return url


def _split_title_and_body(text: str, fallback_title: str) -> tuple[str, str]:
    """Pull a one-line title off the top of *text*; remainder is the body."""
    text = text.strip()
    if not text:
        return fallback_title, ""
    lines = text.splitlines()
    title_line = lines[0].strip().lstrip("# ").strip().strip('"')
    if not title_line or len(title_line) > 250:
        return fallback_title, text
    body = "\n".join(lines[1:]).strip() or text
    return title_line[:200], body


def _extract_youtube_video_id(youtube_url: str) -> Optional[str]:
    """Pull the 11-char video id out of any YouTube URL form."""
    try:
        parsed = urlparse(youtube_url)
        host = (parsed.hostname or "").lower()
        if host == "youtu.be":
            vid = parsed.path.lstrip("/").split("/")[0]
            return vid or None
        if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parsed.path == "/watch":
                vid = (parse_qs(parsed.query).get("v") or [""])[0]
                return vid or None
            if parsed.path.startswith("/shorts/"):
                parts = parsed.path.split("/", 2)
                return parts[2].split("/")[0] if len(parts) >= 3 and parts[2] else None
            if parsed.path.startswith("/embed/"):
                parts = parsed.path.split("/", 2)
                return parts[2].split("/")[0] if len(parts) >= 3 and parts[2] else None
    except Exception:
        return None
    return None


async def _fetch_youtube_captions(video_id: str) -> Optional[str]:
    """Fetch the YouTube caption track (auto-generated or human) and return
    it as plain text. Returns None if the library isn't available, the
    video has no captions, or any fetch error occurs.

    youtube-transcript-api hits YouTube's existing timed-text endpoint —
    same data the YouTube web player uses to render closed captions. Fast
    (~1s for most videos), no auth, no rate-limit concerns at our volume.
    """
    if YouTubeTranscriptApi is None:
        return None
    try:
        # The library is sync; isolate it on the default executor so the
        # asyncio loop isn't blocked.
        def _do_fetch():
            api = YouTubeTranscriptApi()
            return api.fetch(video_id)

        result = await asyncio.to_thread(_do_fetch)
        # FetchedTranscript is iterable of FetchedTranscriptSnippet;
        # each snippet has .text. Concatenate with spaces.
        text_parts = []
        for snippet in result:
            text = getattr(snippet, "text", None) or (
                snippet.get("text") if isinstance(snippet, dict) else None
            )
            if text:
                text_parts.append(text.strip())
        joined = " ".join(text_parts).strip()
        return joined or None
    except Exception as exc:
        logger.debug("youtube-transcript-api failed for %s: %s", video_id, exc)
        return None


async def _fetch_youtube_oembed(youtube_url: str) -> dict:
    """Fetch title + author via YouTube's free oEmbed endpoint. No auth.
    Returns an empty dict on any failure."""
    try:
        # Avoid the cyclic import on module load — _SSL_CTX is the same
        # certifi-backed context the rest of the crawler uses.
        from app.services.crawler import _SSL_CTX

        async with httpx.AsyncClient(timeout=5.0, verify=_SSL_CTX) as client:
            response = await client.get(
                "https://www.youtube.com/oembed",
                params={"url": youtube_url, "format": "json"},
            )
            if response.status_code == 200:
                return response.json() or {}
    except Exception as exc:
        logger.debug("YouTube oEmbed fetch failed for %s: %s", youtube_url, exc)
    return {}


async def _fetch_youtube_title_via_html(youtube_url: str) -> Optional[str]:
    """Last-resort title extraction: scrape the watch page HTML for
    ``<title>`` or ``<meta property="og:title">``. Used when oEmbed fails
    (unlisted/age-restricted/region-blocked content).
    """
    try:
        from app.services.crawler import _SSL_CTX, _OG_TITLE_RE, _TITLE_TAG_RE, _clean_title

        async with httpx.AsyncClient(
            timeout=5.0,
            follow_redirects=True,
            verify=_SSL_CTX,
            headers={"User-Agent": "Synapse-Bot/1.0 (research tool)"},
        ) as client:
            response = await client.get(youtube_url)
            if response.status_code != 200:
                return None
            html = response.text
        # og:title is more reliable than <title> on YouTube — the latter
        # often includes the " - YouTube" suffix.
        m = _OG_TITLE_RE.search(html)
        if m:
            cleaned = _clean_title(m.group(1))
            if cleaned and not cleaned.lower().startswith(("http://", "https://")):
                return cleaned
        m = _TITLE_TAG_RE.search(html)
        if m:
            cleaned = _clean_title(m.group(1))
            if cleaned and not cleaned.lower().startswith(("http://", "https://")):
                return cleaned
    except Exception as exc:
        logger.debug("YouTube HTML title scrape failed for %s: %s", youtube_url, exc)
    return None


async def gemini_ingest_youtube(
    url: str,
    *,
    api_key: Optional[str] = None,
) -> Optional[dict[str, str]]:
    """Two-tier YouTube ingest:

    1. **Captions API** (primary, ~1–2s): pull the video's caption track
       via ``youtube-transcript-api``; fetch title via YouTube oEmbed.
       Works for ~95% of YouTube videos (anything with auto-generated or
       human captions, which is most modern content).

    2. **Gemini file_uri video processing** (fallback, ~30–90s): for the
       rare caption-less videos, fall through to Gemini's native video
       understanding. Slower and may time out on long videos, but it's
       the only Gemini-supported way to extract content otherwise.
    """
    settings = get_settings()
    canonical_url = _normalize_youtube_url(url)

    # ---------- Tier 1: captions API ---------------------------------------
    video_id = _extract_youtube_video_id(canonical_url)
    if video_id:
        captions = await _fetch_youtube_captions(video_id)
        if captions and len(captions) >= 200:
            # Got a usable transcript. Resolve the title through a
            # progressive fallback chain — oEmbed first, HTML scrape if
            # that fails, video-id-based label if nothing else works. We
            # never want to leave the source with a raw URL as title; the
            # sidebar header would render as "youtube.com/watch?v=..."
            # which is useless to the user.
            metadata = await _fetch_youtube_oembed(canonical_url)
            title = (metadata.get("title") or "").strip()
            if not title:
                title = (await _fetch_youtube_title_via_html(canonical_url)) or ""
            if not title:
                title = f"YouTube video ({video_id})"

            author = (metadata.get("author_name") or "").strip()
            # Prepend the title so the corpus snippet feels well-attributed.
            body = captions[: settings.max_document_chars]
            full_text = f"{title}\n\nBy: {author}\n\n{body}" if author else f"{title}\n\n{body}"
            logger.info(
                "YouTube captions OK — title=%r, %d caption chars: %s",
                title, len(captions), canonical_url,
            )
            return {"title": title, "text": full_text}
        else:
            logger.info(
                "YouTube captions unavailable for %s; falling back to Gemini video ingest",
                canonical_url,
            )

    # ---------- Tier 2: Gemini video file_uri (fallback) -------------------
    client = get_genai_client(api_key)
    types = get_genai_types()
    if client is None or types is None:
        logger.warning("YouTube fallback ingest skipped — no Gemini client")
        return None
    logger.info("Gemini YouTube file_uri ingest: %s", canonical_url)

    # Use LOW media resolution by default so multi-hour videos fit. Most of the
    # extractable content lives in the audio track; ~64 tokens/frame is plenty
    # for visual context. Falls back to default if MEDIA_RESOLUTION_LOW isn't
    # available in this SDK version.
    #
    # Note: VideoMetadata.end_offset would let us cap to a shorter window
    # (e.g. first 20 minutes) but it's currently unsupported by the public
    # Gemini API ("video_metadata parameter is not supported"). Worker.py
    # gives YouTube-containing notebooks a longer deadline instead.
    config_kwargs = {}
    try:
        if hasattr(types, "MediaResolution"):
            config_kwargs["media_resolution"] = types.MediaResolution.MEDIA_RESOLUTION_LOW
    except Exception:
        pass

    contents = types.Content(
        parts=[
            types.Part(
                file_data=types.FileData(
                    file_uri=canonical_url,
                    mime_type="video/*",
                )
            ),
            types.Part(text=(
                "This is a video. Produce a structured transcript that "
                "captures (1) the speaker's main claims, (2) any technical "
                "content shown or said, (3) examples or demos depicted "
                "visually. Output as plain text in clean paragraphs, "
                "approximately 2000-3000 words. Begin the very first line "
                "with the video's title (no markdown, no quotes)."
            )),
        ]
    )

    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs) if config_kwargs else None,
        )
    except Exception as exc:
        logger.warning("Gemini YouTube ingest failed for %s: %s", canonical_url, exc)
        return None

    text = (getattr(response, "text", "") or "").strip()
    if not text or len(text) < 100:
        logger.warning("Gemini returned empty/short transcript for %s (%d chars)", canonical_url, len(text))
        return None

    # Same progressive title fallback as the captions path — never leave
    # the title as a raw YouTube URL.
    fallback_title = (
        await _fetch_youtube_title_via_html(canonical_url)
        or (f"YouTube video ({video_id})" if video_id else canonical_url)
    )
    title, body = _split_title_and_body(text, fallback_title=fallback_title)
    truncated = body[: settings.max_document_chars]
    logger.info("YouTube ingest OK — title=%r, %d chars", title, len(truncated))
    return {"title": title, "text": truncated}


async def gemini_ingest_pdf(
    url: str,
    *,
    api_key: Optional[str] = None,
    download_timeout: float = 30.0,
) -> Optional[dict[str, str]]:
    """Download a PDF and have Gemini extract its full text."""
    client = get_genai_client(api_key)
    types = get_genai_types()
    if client is None or types is None:
        logger.warning("PDF ingest skipped — no Gemini client")
        return None

    settings = get_settings()
    logger.info("Gemini PDF ingest: %s", url)

    # Step 1: download bytes ourselves so SSL / redirects use our hardened client
    from app.services.crawler import _SSL_CTX  # local import to avoid cycle at module load

    try:
        async with httpx.AsyncClient(
            timeout=download_timeout,
            follow_redirects=True,
            verify=_SSL_CTX,
            headers={"User-Agent": "Synapse-Bot/1.0 (research tool)"},
        ) as http:
            r = await http.get(url)
            r.raise_for_status()
            pdf_bytes = r.content
    except Exception as exc:
        logger.warning("PDF download failed for %s: %s", url, exc)
        return None

    if len(pdf_bytes) < 1024:
        logger.warning("PDF body too small (%d bytes) — likely an error page: %s", len(pdf_bytes), url)
        return None

    # Inline data limit is ~20MB. Beyond that we'd switch to the Files API,
    # but research papers are virtually always under that ceiling.
    if len(pdf_bytes) > 20 * 1024 * 1024:
        logger.warning("PDF too large for inline ingest (%d bytes), skipping: %s", len(pdf_bytes), url)
        return None

    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=types.Content(
                parts=[
                    types.Part(
                        inline_data=types.Blob(
                            mime_type="application/pdf",
                            data=pdf_bytes,
                        )
                    ),
                    types.Part(text=(
                        "Extract the full readable content of this PDF. Preserve "
                        "headings, lists, and paragraph breaks. Skip page numbers, "
                        "running headers/footers, and bibliography entries. "
                        "Begin the very first line with the document's title "
                        "(no markdown, no quotes)."
                    )),
                ]
            ),
        )
    except Exception as exc:
        logger.warning("Gemini PDF parse failed for %s: %s", url, exc)
        return None

    text = (getattr(response, "text", "") or "").strip()
    if not text or len(text) < 100:
        logger.warning("Gemini returned empty/short PDF text for %s", url)
        return None

    title, body = _split_title_and_body(text, fallback_title=url)
    truncated = body[: settings.max_document_chars]
    logger.info("PDF ingest OK — title=%r, %d chars", title, len(truncated))
    return {"title": title, "text": truncated}


async def gemini_ingest_via_tools(
    url: str,
    *,
    api_key: Optional[str] = None,
) -> Optional[dict[str, str]]:
    """Universal fallback ingester — let Gemini fetch the URL via its tools.

    Used in two places:

    1. **First-try path** for known bot-walled domains (Twitter/X, Reddit,
       LinkedIn, Threads). Trafilatura would just fail there, so we go
       directly to tools-based ingest.
    2. **Last-resort fallback** for any URL where the trafilatura+Firecrawl
       path produced no usable content.

    Mechanism: Gemini calls ``url_context`` (to fetch the page directly) and
    ``google_search`` (to find indexed/cached content) and synthesises a
    transcript. Sentence-level fidelity is lower than a real scraper would
    give — but it's the only way to extract content that no scraper can
    reach. Cost is one Gemini call per source.
    """
    client = get_genai_client(api_key)
    types = get_genai_types()
    if client is None or types is None:
        logger.warning("Tools-based ingest skipped — no Gemini client")
        return None

    settings = get_settings()
    logger.info("Gemini tools-based ingest: %s", url)

    # Build the tool list defensively — different SDK versions expose
    # different surface areas. We want both url_context and google_search
    # if available; either alone is enough to make this useful.
    tools = []
    try:
        if hasattr(types, "UrlContext"):
            tools.append(types.Tool(url_context=types.UrlContext()))
    except Exception as exc:
        logger.debug("url_context tool unavailable: %s", exc)
    try:
        tools.append(types.Tool(google_search=types.GoogleSearch()))
    except Exception as exc:
        logger.debug("google_search tool unavailable: %s", exc)

    if not tools:
        logger.warning("No grounding tools available for tools-based ingest")
        return None

    prompt = (
        f"Read the content at this URL: {url}\n\n"
        "Produce a complete, faithful transcript of the content:\n"
        "- For YouTube videos: include the video's title, the speaker/author, "
        "and a faithful transcript of what was said. Capture key claims, "
        "examples, demos, and conclusions. ~2000-3000 words.\n"
        "- For Twitter/X posts: include the author, the full post text "
        "verbatim, key replies in the thread if visible.\n"
        "- For Reddit threads: include the thread title, the original "
        "post body, and the most-upvoted or most-relevant comments.\n"
        "- For LinkedIn posts/articles: include the author, post text, "
        "and any visible engagement context.\n"
        "- For articles or any other web content: extract the full body "
        "text verbatim.\n\n"
        "Begin the very first line with a short title summarising the "
        "content (video title, post topic, tweet's first sentence, thread "
        "title) — no markdown, no quotes.\n\n"
        "If you genuinely cannot access this content (deleted, private, "
        "geo-blocked, etc.), respond with only the single word: "
        "NOT_ACCESSIBLE"
    )

    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(tools=tools),
        )
    except Exception as exc:
        logger.warning("Gemini tools ingest failed for %s: %s", url, exc)
        return None

    text = (getattr(response, "text", "") or "").strip()
    if not text or "NOT_ACCESSIBLE" in text[:50] or len(text) < 100:
        logger.warning(
            "Gemini tools ingest empty/inaccessible for %s (%d chars, prefix=%r)",
            url, len(text), text[:80],
        )
        return None

    title, body = _split_title_and_body(text, fallback_title=url)
    truncated = body[: settings.max_document_chars]
    logger.info("Tools ingest OK — title=%r, %d chars: %s", title, len(truncated), url)
    return {"title": title, "text": truncated}
