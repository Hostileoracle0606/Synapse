from __future__ import annotations

"""Async pipeline for notebook processing.

Stages:

1. **Seed processing** – store seed text and produce a fast summary.
2. **Discovery** – find related sources via Gemini grounding (3 parallel
   type-scoped calls: articles, papers, videos).
3. **Concurrent crawl + summarize** – fetch each URL and summarize each
   source in parallel, streamed (every source goes crawl → summarize as
   one task) under a global notebook-deadline. Bounded by per-stage
   semaphores. The full crawled text stays in ``source.content`` and is
   later loaded into the chat prompt as long-context.
4. **Graph construction** – keyword-overlap edges with no LLM calls.

The per-request Gemini key is threaded all the way down so the BYOK flow
works end-to-end without leaking keys to env-level state.

Dispatch model: ``enqueue_notebook_processing`` schedules
``_process_notebook_async`` as an ``asyncio.create_task`` on the FastAPI
event loop. The route handler returns immediately; the pipeline runs in
the background and updates the in-memory repository as work progresses.
No Celery, no Redis, no separate worker process — this runs in the same
uvicorn process and shares the in-memory repo with HTTP handlers.
"""

import asyncio
import logging
import re
import time
from typing import Optional

import httpx


def _normalize_title(title: str) -> str:
    """Normalise a title for dedup comparison.

    Lowercase, strip surrounding quotes/punctuation/whitespace, collapse
    internal whitespace. Keeps internal punctuation so "Attention is all
    you need!" and "Attention is all you need" map together but
    "Attention" and "Attention Mechanism" stay distinct.
    """
    if not title:
        return ""
    t = title.lower().strip()
    # Drop leading/trailing quotes, periods, dashes, whitespace
    t = re.sub(r"^[\"\'“”.\-—\s]+", "", t)
    t = re.sub(r"[\"\'“”.\-—\s]+$", "", t)
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t)
    return t


async def _classify_discovered_sources(discovered: list[dict]) -> list[str]:
    """For each discovered URL, do a quick HEAD probe to determine its real
    source_type up front so the formation graph can color nodes correctly
    from t=0 — instead of every node showing as a generic blue 'webpage'
    until the deeper crawl finishes much later.

    Why this is needed: Gemini grounding wraps every URL in an opaque
    ``vertexaisearch.cloud.google.com/grounding-api-redirect/...`` string,
    so we can't tell type from the URL alone. One HEAD probe per source
    resolves the redirect and picks up the Content-Type cheaply (~200ms
    each, all run in parallel = <1s overhead total).

    Falls back to "webpage" on any failure.
    """
    from app.services.crawler import _looks_like_pdf, _resolve_final_url_and_type
    from app.services.gemini_ingest import is_tools_fallback_url, is_youtube_url

    async def _classify_one(item: dict) -> str:
        url = (item or {}).get("url") or ""
        if not url:
            return "webpage"
        try:
            final_url, content_type = await asyncio.wait_for(
                _resolve_final_url_and_type(url),
                timeout=4.0,
            )
        except Exception:
            return "webpage"

        if is_youtube_url(final_url) or is_youtube_url(url):
            return "youtube"
        if (
            _looks_like_pdf(url, "")
            or _looks_like_pdf(final_url, "")
            or content_type == "application/pdf"
        ):
            return "pdf"
        if is_tools_fallback_url(final_url) or is_tools_fallback_url(url):
            return "social"
        return "webpage"

    if not discovered:
        return []
    return await asyncio.gather(*[_classify_one(item) for item in discovered])

logger = logging.getLogger(__name__)

CRAWL_CONCURRENCY = 5      # max parallel URL fetches
SUMMARY_CONCURRENCY = 3    # max parallel summarize tasks
# PDF parsing via Gemini ≈ 5–30s; YouTube video ingest ≈ 30–120s for longer
# lectures. Webpage crawls finish in under 30s. 180s is the worst-case ceiling.
CRAWL_TIMEOUT = 180.0

from app.config import get_settings

settings = get_settings()


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    msg = str(exc).lower()
    return "rate" in msg or "quota" in msg


async def _retry_async(coro_factory, source_id: str, step_name: str, max_attempts: int = 3):
    delays = [1, 2, 4]
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            if _is_transient_error(exc) and attempt < max_attempts - 1:
                logger.warning(
                    "Transient error in %s for source %s (attempt %d): %s",
                    step_name, source_id, attempt + 1, exc,
                )
                await asyncio.sleep(delays[attempt])
            else:
                break
    raise last_exc  # type: ignore[misc]


async def _summarize_one_source(
    source_id: str,
    title: str,
    text: str,
    *,
    summarize_document,
    update_source,
    api_key: Optional[str],
) -> bool:
    """Summarize one source. Returns True on success.

    Note: no embeddings, no chunks. The crawled `text` is already stored on
    the source record (via update_source(content=...)); we just attach a
    summary and mark the source ready.
    """
    if text is None or not text.strip():
        await update_source(source_id, status="error", error_message="Content is empty")
        return False
    if len(text.strip()) < 100:
        await update_source(source_id, status="error", error_message="Content too short to process")
        return False

    try:
        summary = await _retry_async(
            lambda: summarize_document(text, title, api_key=api_key),
            source_id,
            "summarize",
        )
    except Exception as exc:
        logger.error("Summary failed for source %s: %s", source_id, exc)
        await update_source(source_id, status="error", error_message=str(exc))
        return False

    await update_source(
        source_id,
        summary=summary,
        status="ready",
        error_message=None,
    )
    return True


async def _process_notebook_async(notebook_id: str, seed_text: str, api_key: Optional[str] = None):
    from app.database import (
        create_edge,
        create_source,
        get_sources,
        update_notebook_status,
        update_source,
    )
    from app.services.crawler import smart_crawl_url
    from app.services.discovery import discover_related_sources
    from app.services.graph import compute_edges
    from app.services.processor import summarize_document

    _settings = get_settings()
    # Keyword-overlap (weighted Jaccard) lives in a different range than the
    # legacy cosine threshold (0.40). Anything above ~0.25 produces zero edges.
    # If the user explicitly set a low threshold via env, respect it; otherwise
    # default to 0.05 which is appropriate for the new scoring.
    _env_threshold = float(getattr(_settings, "edge_similarity_threshold", 0.4))
    _edge_threshold = _env_threshold if _env_threshold <= 0.25 else 0.05

    _summary_deps = dict(
        summarize_document=summarize_document,
        update_source=update_source,
        api_key=api_key,
    )

    t0 = time.monotonic()

    # ── Stages 1+2 PARALLEL ───────────────────────────────────────────────
    # Seed summary and discovery are independent after seed_text is known —
    # discovery only needs the raw text, the summary is a UI nicety. Run
    # them concurrently so total = max(seed_summary, discovery), not sum.
    seed_source = await create_source(notebook_id, None, "Seed Document", "seed")
    await update_source(seed_source["id"], content=seed_text, status="processing")

    seed_summary_task = asyncio.create_task(
        _summarize_one_source(
            seed_source["id"], "Seed Document", seed_text, **_summary_deps,
        )
    )
    discovery_task = asyncio.create_task(
        discover_related_sources(
            seed_text,
            max_results=_settings.max_discovery_results,
            api_key=api_key,
        )
    )

    # Wait for discovery — Stages 3+4 need the URLs. Seed summary continues
    # in the background; we'll await it later (it almost always finishes
    # first since summary < discovery).
    discovered = await discovery_task

    # Pre-classify each discovered URL via parallel HEAD probes so the
    # formation graph can colour nodes correctly *immediately* — instead of
    # showing every node as generic blue until the deeper crawl reveals
    # its real type 10–15s later.
    detected_types = await _classify_discovered_sources(discovered)
    if detected_types:
        type_summary = {}
        for t in detected_types:
            type_summary[t] = type_summary.get(t, 0) + 1
        logger.info("Pre-classified discovered sources: %s", type_summary)

    source_records = []
    for item, detected_type in zip(discovered, detected_types):
        record = await create_source(
            notebook_id=notebook_id,
            url=item["url"],
            title=item["title"],
            source_type=detected_type,
        )
        source_records.append(record)
    logger.info(
        "Stages 1+2 (parallel seed+discovery): %d discovered sources in %.1fs",
        len(source_records), time.monotonic() - t0,
    )

    # ── Stages 3+4 STREAMED with hard deadline ─────────────────────────────
    # Each source goes crawl → summarize as one task; both semaphores apply.
    # A *global* deadline (settings.notebook_crawl_deadline_s) caps the whole
    # phase: anything still running at the deadline is cancelled and its
    # source marked "Skipped — exceeded notebook time budget". This trades
    # exhaustive ingestion for predictable wall-clock time.
    t2 = time.monotonic()
    crawl_sem = asyncio.Semaphore(CRAWL_CONCURRENCY)
    summary_sem = asyncio.Semaphore(SUMMARY_CONCURRENCY)

    crawl_success_count = 0
    summarize_success_count = 0

    async def _crawl_then_summarize(record: dict) -> None:
        nonlocal crawl_success_count, summarize_success_count

        try:
            # ----- crawl phase ----------------------------------------------
            async with crawl_sem:
                await update_source(record["id"], status="crawling")
                try:
                    crawled = await asyncio.wait_for(
                        smart_crawl_url(
                            record["url"],
                            record.get("source_type", "webpage"),
                            api_key=api_key,
                        ),
                        timeout=CRAWL_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    logger.warning("Crawl timed out after %.0fs: %s", CRAWL_TIMEOUT, record["url"])
                    await update_source(record["id"], status="error", error_message="Crawl timed out")
                    return
                except asyncio.CancelledError:
                    raise  # re-raise so the outer handler marks us skipped
                except Exception as exc:
                    logger.warning("Crawl failed for %s: %s", record["url"], exc)
                    await update_source(record["id"], status="error", error_message=str(exc))
                    return
                if not crawled:
                    await update_source(record["id"], status="error", error_message="Failed to fetch")
                    return
                title = crawled.get("title") or record["title"]
                text = crawled.get("text", "")
                detected_type = crawled.get("source_type") or record.get("source_type", "webpage")
                # Replace the original (vertexaisearch redirect) URL with
                # the post-redirect URL. This makes downstream URL-based
                # dedup work and gives the user a clickable real link.
                resolved_url = crawled.get("final_url") or record.get("url")
                update_kwargs = dict(
                    content=text,
                    title=title,
                    source_type=detected_type,
                    status="processing",
                )
                if resolved_url:
                    update_kwargs["url"] = resolved_url
                await update_source(record["id"], **update_kwargs)
                crawl_success_count += 1
            # crawl_sem released here — next URL can start crawling now

            # ----- summarize phase ------------------------------------------
            async with summary_sem:
                ok = await _summarize_one_source(
                    record["id"], title, text, **_summary_deps,
                )
                if ok:
                    summarize_success_count += 1
        except asyncio.CancelledError:
            # Global deadline fired and we were still in flight. Mark the
            # source as skipped so the UI shows it clearly (not "stuck").
            try:
                await update_source(
                    record["id"],
                    status="error",
                    error_message="Skipped — exceeded notebook time budget",
                )
            except Exception:
                pass
            raise

    deadline = float(getattr(_settings, "notebook_crawl_deadline_s", 90.0))
    tasks = [asyncio.create_task(_crawl_then_summarize(r)) for r in source_records]
    if tasks:
        done, pending = await asyncio.wait(tasks, timeout=deadline)
        # Cancel anything still running and let it finish cancelling cleanly.
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        skipped = len(pending)
    else:
        skipped = 0
    logger.info(
        "Stages 3+4 (streamed, deadline=%.0fs): %d/%d crawled, %d summarized, %d skipped in %.1fs",
        deadline, crawl_success_count, len(source_records),
        summarize_success_count, skipped, time.monotonic() - t2,
    )

    # Make sure the seed summary task has finished before we build edges
    # (the seed source's status / summary feeds into the graph). It usually
    # completed long before Stages 3+4 finished, but await is cheap.
    try:
        await seed_summary_task
    except Exception as exc:
        logger.warning("Seed summary task failed: %s", exc)

    # ── Dedup: URL-primary, title-fallback ────────────────────────────────
    # Two-pass dedup. URL pass uses the *resolved* post-redirect URL stored
    # on each source after smart_crawl_url; this catches the common case
    # of multiple Gemini grounding redirects that all point at the same
    # article. The title fallback then catches the rarer case of the same
    # article hosted at multiple canonical URLs (mirrors, syndication, etc).
    from app.database import delete_source as _delete_source

    pre_dedup = await get_sources(notebook_id)

    def _better(a: dict, b: dict) -> dict:
        """Pick the source with more content (proxy for richer crawl)."""
        return a if len((a.get("content") or "").strip()) >= len((b.get("content") or "").strip()) else b

    by_url: dict[str, dict] = {}
    duplicates_to_drop: list[str] = []

    # Pass 1: URL dedup (uses normalized url — strips trailing slashes,
    # query strings collapse to canonical form).
    for src in pre_dedup:
        if src.get("source_type") == "seed":
            continue
        if src.get("status") != "ready":
            continue
        url = (src.get("url") or "").strip().rstrip("/")
        if not url:
            continue
        url_key = url.lower()
        existing = by_url.get(url_key)
        if existing is None:
            by_url[url_key] = src
        else:
            winner = _better(src, existing)
            loser = existing if winner is src else src
            by_url[url_key] = winner
            duplicates_to_drop.append(loser["id"])

    # Pass 2: title dedup over the URL-deduped survivors. Catches same-
    # article-different-canonical-URL cases.
    by_norm_title: dict[str, dict] = {}
    for src in by_url.values():
        norm = _normalize_title(src.get("title") or "")
        if not norm:
            continue
        existing = by_norm_title.get(norm)
        if existing is None:
            by_norm_title[norm] = src
        else:
            winner = _better(src, existing)
            loser = existing if winner is src else src
            by_norm_title[norm] = winner
            duplicates_to_drop.append(loser["id"])

    if duplicates_to_drop:
        for sid in duplicates_to_drop:
            await _delete_source(sid)
        logger.info(
            "Dedup: dropped %d duplicate source(s) (url-primary, title-fallback)",
            len(duplicates_to_drop),
        )

    # ── Stage 5: Graph construction (keyword overlap, no LLM) ────────────
    t4 = time.monotonic()
    all_sources = await get_sources(notebook_id)
    ready_sources = [s for s in all_sources if s.get("status") == "ready"]
    edges = compute_edges(ready_sources, threshold=_edge_threshold)
    for edge in edges:
        await create_edge(
            notebook_id=notebook_id,
            source_a=edge["source_a"],
            source_b=edge["source_b"],
            similarity=edge["similarity"],
            relationship=edge.get("relationship"),
        )
    logger.info("Stage 5 (graph): %d edges in %.2fs", len(edges), time.monotonic() - t4)

    await update_notebook_status(notebook_id, "ready")
    logger.info("Notebook %s completed in %.1fs total", notebook_id, time.monotonic() - t0)


async def _safe_process_in_background(
    notebook_id: str, seed_text: str, api_key: Optional[str],
):
    """Wrap the pipeline so a crash flips notebook.status to "error" instead
    of leaving the task silently dead. The outer asyncio.create_task in
    `enqueue_notebook_processing` would otherwise swallow the exception.
    """
    from app.database import update_notebook_status

    try:
        await _process_notebook_async(notebook_id, seed_text, api_key=api_key)
    except Exception as exc:
        logger.error(
            "Notebook %s background pipeline failed: %s",
            notebook_id, exc, exc_info=True,
        )
        try:
            await update_notebook_status(notebook_id, "error")
        except Exception as inner:
            logger.error("Could not mark notebook %s as error: %s", notebook_id, inner)


def enqueue_notebook_processing(
    notebook_id: str, seed_text: str, api_key: Optional[str] = None,
):
    """Schedule the notebook pipeline as a background asyncio task.

    The route handler returns immediately after this call. The pipeline
    runs concurrently on the same event loop as HTTP requests — sharing
    in-memory state with no IPC overhead. There is no separate worker
    process, no broker, no Celery; the FastAPI server is the worker.
    """
    asyncio.create_task(_safe_process_in_background(notebook_id, seed_text, api_key))
