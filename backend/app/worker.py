from __future__ import annotations

"""Celery task & async pipeline for notebook processing.

The pipeline is structured into bounded-concurrency stages:

1. **Seed processing** – process the seed document (sequential).
2. **Discovery** – find related sources via Gemini (sequential, single API call).
3. **Concurrent crawl** – fetch discovered URLs in parallel, capped by
   ``CRAWL_CONCURRENCY``.
4. **Concurrent process** – summarise + embed each crawled source in parallel,
   capped by ``PROCESS_CONCURRENCY``.  Within each source, summary and chunk
   embedding run concurrently via ``asyncio.gather``.
5. **Graph construction** – compute edges and labels (sequential, needs all
   sources).

Each source is independent after discovery, so a single failure does not block
the rest.
"""

import asyncio
import logging
import time

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Concurrency knobs – conservative defaults, tuneable via env or direct edit
# ---------------------------------------------------------------------------
CRAWL_CONCURRENCY = 5      # max parallel URL fetches
PROCESS_CONCURRENCY = 3    # max parallel summarise+embed tasks
CRAWL_TIMEOUT = 60.0       # max seconds per URL (httpx 15s + Firecrawl 30s + headroom)

# ---------------------------------------------------------------------------
# Celery application
# ---------------------------------------------------------------------------
try:
    from celery import Celery
except Exception:  # pragma: no cover - optional dependency
    class _DummyConf:
        task_always_eager = False
        task_store_eager_result = False

    class Celery:  # type: ignore[override]
        def __init__(self, *args, **kwargs):
            self.conf = _DummyConf()

        def task(self, name=None):
            def decorator(func):
                func.delay = func
                return func
            return decorator

from app.config import get_settings

settings = get_settings()
celery_app = Celery("synapse", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_always_eager = settings.celery_task_always_eager
celery_app.conf.task_store_eager_result = settings.celery_task_always_eager


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Retry / transient-error helpers
# ---------------------------------------------------------------------------

def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    msg = str(exc).lower()
    return "rate" in msg or "quota" in msg


async def _retry_async(coro_factory, source_id: str, step_name: str, max_attempts: int = 3):
    """Call *coro_factory()* with exponential-backoff retry for transient errors.

    Returns the result of the coroutine on success.  Raises the last exception
    on final failure.
    """
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


# ---------------------------------------------------------------------------
# Per-source processing (validate → summarise ∥ embed → persist)
# ---------------------------------------------------------------------------

async def _process_single_source(
    source_id: str,
    title: str,
    text: str,
    notebook_id: str,
    *,
    summarize_document,
    embed_chunks,
    replace_source_chunks,
    update_source,
) -> bool:
    """Process one source end-to-end.  Returns True on success."""

    # --- Input validation (before any API call) ---
    if text is None or not text.strip():
        await update_source(source_id, status="error", error_message="Content is empty")
        return False
    if len(text.strip()) < 100:
        await update_source(source_id, status="error", error_message="Content too short to process")
        return False

    # --- Summarise + embed in parallel ---
    try:
        summary, chunks = await asyncio.gather(
            _retry_async(lambda: summarize_document(text, title), source_id, "summarize"),
            _retry_async(lambda: embed_chunks(text), source_id, "embed"),
        )
    except Exception as exc:
        logger.error("Processing failed for source %s: %s", source_id, exc)
        await update_source(source_id, status="error", error_message=str(exc))
        return False

    if not chunks:
        await update_source(source_id, status="error", error_message="Failed to embed source content")
        return False

    # --- Persist results immediately ---
    await replace_source_chunks(source_id, notebook_id, chunks)
    await update_source(
        source_id,
        summary=summary,
        embedding=None,
        status="ready",
        error_message=None,
    )
    return True


# ---------------------------------------------------------------------------
# Full async pipeline
# ---------------------------------------------------------------------------

async def _process_notebook_async(notebook_id: str, seed_text: str):
    from app.database import (
        create_edge,
        create_source,
        get_notebook_chunks,
        get_sources,
        replace_source_chunks,
        update_notebook_status,
        update_source,
    )
    from app.services.crawler import smart_crawl_url
    from app.services.discovery import discover_related_sources
    from app.services.graph import compute_edges, generate_edge_labels
    from app.services.processor import embed_chunks, summarize_document

    _settings = get_settings()
    _edge_threshold = getattr(_settings, "edge_similarity_threshold", 0.4)

    # Shared kwargs threaded into helper functions
    _deps = dict(
        summarize_document=summarize_document,
        embed_chunks=embed_chunks,
        replace_source_chunks=replace_source_chunks,
        update_source=update_source,
    )

    t0 = time.monotonic()

    # ── Stage 1: Seed ────────────────────────────────────────────────────
    seed_source = await create_source(notebook_id, None, "Seed Document", "seed")
    await update_source(seed_source["id"], content=seed_text, status="processing")
    await _process_single_source(
        seed_source["id"], "Seed Document", seed_text, notebook_id, **_deps,
    )
    logger.info("Stage 1 (seed): %.1fs", time.monotonic() - t0)

    # ── Stage 2: Discovery ───────────────────────────────────────────────
    t1 = time.monotonic()
    discovered = await discover_related_sources(
        seed_text, max_results=_settings.max_discovery_results,
    )
    source_records = []
    for item in discovered:
        record = await create_source(
            notebook_id=notebook_id,
            url=item["url"],
            title=item["title"],
            source_type="webpage",
        )
        source_records.append(record)
    logger.info("Stage 2 (discovery): %d sources in %.1fs", len(source_records), time.monotonic() - t1)

    # ── Stage 3: Concurrent crawl ────────────────────────────────────────
    t2 = time.monotonic()
    crawl_sem = asyncio.Semaphore(CRAWL_CONCURRENCY)

    async def _crawl_one(record: dict) -> dict | None:
        async with crawl_sem:
            await update_source(record["id"], status="crawling")
            try:
                crawled = await asyncio.wait_for(
                    smart_crawl_url(record["url"], record.get("source_type", "webpage")),
                    timeout=CRAWL_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.warning("Crawl timed out after %.0fs: %s", CRAWL_TIMEOUT, record["url"])
                await update_source(record["id"], status="error", error_message="Crawl timed out")
                return None
            except Exception as exc:
                logger.warning("Crawl failed for %s: %s", record["url"], exc)
                await update_source(record["id"], status="error", error_message=str(exc))
                return None
            if not crawled:
                await update_source(record["id"], status="error", error_message="Failed to fetch")
                return None
            title = crawled.get("title") or record["title"]
            text = crawled.get("text", "")
            await update_source(record["id"], content=text, title=title, status="processing")
            return {**record, "title": title, "text": text}

    crawl_results = await asyncio.gather(
        *[_crawl_one(r) for r in source_records],
        return_exceptions=True,
    )
    crawled_sources = []
    for result in crawl_results:
        if isinstance(result, Exception):
            logger.warning("Crawl task raised: %s", result)
        elif result is not None:
            crawled_sources.append(result)
    logger.info(
        "Stage 3 (crawl): %d/%d in %.1fs",
        len(crawled_sources), len(source_records), time.monotonic() - t2,
    )

    # ── Stage 4: Concurrent process (summarise ∥ embed per source) ───────
    t3 = time.monotonic()
    process_sem = asyncio.Semaphore(PROCESS_CONCURRENCY)

    async def _process_one(info: dict) -> None:
        async with process_sem:
            await _process_single_source(
                info["id"], info["title"], info["text"], notebook_id, **_deps,
            )

    await asyncio.gather(
        *[_process_one(s) for s in crawled_sources],
        return_exceptions=True,
    )
    logger.info("Stage 4 (process): %d sources in %.1fs", len(crawled_sources), time.monotonic() - t3)

    # ── Stage 5: Graph construction ──────────────────────────────────────
    t4 = time.monotonic()
    docs_by_id = {item["id"]: item for item in await get_sources(notebook_id)}
    notebook_chunks = await get_notebook_chunks(notebook_id)
    edges = compute_edges(list(docs_by_id.values()), notebook_chunks, threshold=_edge_threshold)
    labeled_edges = await generate_edge_labels(edges, docs_by_id)
    for edge in labeled_edges:
        await create_edge(
            notebook_id=notebook_id,
            source_a=edge["source_a"],
            source_b=edge["source_b"],
            similarity=edge["similarity"],
            relationship=edge.get("relationship"),
        )
    logger.info("Stage 5 (graph): %d edges in %.1fs", len(labeled_edges), time.monotonic() - t4)

    await update_notebook_status(notebook_id, "ready")
    logger.info("Notebook %s completed in %.1fs total", notebook_id, time.monotonic() - t0)


# ---------------------------------------------------------------------------
# Celery task entry-point
# ---------------------------------------------------------------------------

@celery_app.task(name="process_notebook")
def process_notebook(notebook_id: str, seed_text: str):
    try:
        run_async(_process_notebook_async(notebook_id, seed_text))
    except Exception as e:
        from app.database import update_notebook_status
        logger.error("Notebook %s failed during processing: %s", notebook_id, e, exc_info=True)
        run_async(update_notebook_status(notebook_id, "error"))
        raise


def enqueue_notebook_processing(notebook_id: str, seed_text: str):
    from app.database import update_notebook_status

    try:
        process_notebook.delay(notebook_id, seed_text)
    except Exception as e:
        logger.error("Failed to enqueue notebook %s: %s", notebook_id, e)
        run_async(update_notebook_status(notebook_id, "error"))
        return
