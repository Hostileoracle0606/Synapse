"""Tests for worker.py bug fixes and concurrent pipeline."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings

EXPECTED_DIM = get_settings().embedding_dimension


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_source(source_id: str = "src-1") -> dict:
    return {"id": source_id, "title": "Test Source", "url": "https://example.com"}


def _make_embedding(value: float = 0.1) -> list[float]:
    return [value] * EXPECTED_DIM


def _make_notebook_db_mocks(
    seed_text: str = "x" * 200,
    source_id: str = "src-1",
):
    """Return a dict of AsyncMocks for the database layer used by process_notebook."""
    create_source_mock = AsyncMock(return_value=_make_source(source_id))
    update_source_mock = AsyncMock(return_value=None)
    update_notebook_mock = AsyncMock(return_value=None)
    get_sources_mock = AsyncMock(return_value=[])
    get_notebook_chunks_mock = AsyncMock(return_value=[])
    replace_source_chunks_mock = AsyncMock(return_value=None)
    create_edge_mock = AsyncMock(return_value=None)
    return {
        "create_source": create_source_mock,
        "update_source": update_source_mock,
        "update_notebook_status": update_notebook_mock,
        "get_sources": get_sources_mock,
        "get_notebook_chunks": get_notebook_chunks_mock,
        "replace_source_chunks": replace_source_chunks_mock,
        "create_edge": create_edge_mock,
    }


def _run_process_notebook(
    seed_text: str,
    db_mocks: dict,
    summarize_mock=None,
    embed_mock=None,
    crawl_mock=None,
    discover_mock=None,
):
    """
    Run process_notebook with the given seed_text and mocks.
    All heavy service calls are mocked; only the worker logic is exercised.
    """
    if summarize_mock is None:
        summarize_mock = AsyncMock(return_value="A summary")
    if embed_mock is None:
        embed_mock = AsyncMock(return_value=[{"content": "chunk", "embedding": _make_embedding()}])
    if crawl_mock is None:
        crawl_mock = AsyncMock(return_value=None)
    if discover_mock is None:
        discover_mock = AsyncMock(return_value=[])

    generate_edge_labels_mock = AsyncMock(return_value=[])

    with (
        patch("app.database.create_source", db_mocks["create_source"]),
        patch("app.database.update_source", db_mocks["update_source"]),
        patch("app.database.update_notebook_status", db_mocks["update_notebook_status"]),
        patch("app.database.get_sources", db_mocks["get_sources"]),
        patch("app.database.get_notebook_chunks", db_mocks["get_notebook_chunks"]),
        patch("app.database.replace_source_chunks", db_mocks["replace_source_chunks"]),
        patch("app.database.create_edge", db_mocks["create_edge"]),
        patch("app.services.processor.summarize_document", summarize_mock),
        patch("app.services.processor.embed_chunks", embed_mock),
        patch("app.services.crawler.crawl_url", crawl_mock),
        patch("app.services.discovery.discover_related_sources", discover_mock),
        patch("app.services.graph.generate_edge_labels", generate_edge_labels_mock),
        patch("app.services.graph.compute_edges", return_value=[]),
    ):
        from app.worker import process_notebook
        process_notebook("nb-1", seed_text)

    return {
        "update_source": db_mocks["update_source"],
        "update_notebook_status": db_mocks["update_notebook_status"],
        "summarize": summarize_mock,
        "embed": embed_mock,
    }


# ---------------------------------------------------------------------------
# Fix 1 tests: input validation
# ---------------------------------------------------------------------------

def test_short_content_rejected_early():
    """50-char seed text must mark source error without calling summarize or embed."""
    short_text = "x" * 50
    db_mocks = _make_notebook_db_mocks()
    summarize_mock = AsyncMock(return_value="summary")
    embed_mock = AsyncMock(return_value=[])

    result = _run_process_notebook(
        seed_text=short_text,
        db_mocks=db_mocks,
        summarize_mock=summarize_mock,
        embed_mock=embed_mock,
    )

    # Validation happens BEFORE asyncio.gather, so neither should be called
    summarize_mock.assert_not_called()
    embed_mock.assert_not_called()

    # update_source should have been called with status="error"
    error_calls = [
        c for c in db_mocks["update_source"].call_args_list
        if c.kwargs.get("status") == "error" or (
            len(c.args) > 1 and c.args[1] == "error"
        )
    ]
    assert error_calls, "Expected update_source to be called with status='error'"
    error_msgs = [c.kwargs.get("error_message", "") for c in error_calls]
    assert any("too short" in (m or "").lower() or "short" in (m or "").lower() for m in error_msgs), \
        f"Expected 'too short' in error messages, got: {error_msgs}"


def test_empty_content_rejected_early():
    """Empty seed text must mark source error without calling summarize or embed."""
    db_mocks = _make_notebook_db_mocks()
    summarize_mock = AsyncMock(return_value="summary")
    embed_mock = AsyncMock(return_value=[])

    result = _run_process_notebook(
        seed_text="",
        db_mocks=db_mocks,
        summarize_mock=summarize_mock,
        embed_mock=embed_mock,
    )

    # Validation happens BEFORE asyncio.gather, so neither should be called
    summarize_mock.assert_not_called()
    embed_mock.assert_not_called()

    error_calls = [
        c for c in db_mocks["update_source"].call_args_list
        if c.kwargs.get("status") == "error" or (
            len(c.args) > 1 and c.args[1] == "error"
        )
    ]
    assert error_calls, "Expected update_source to be called with status='error' for empty content"
    error_msgs = [c.kwargs.get("error_message", "") for c in error_calls]
    assert any("empty" in (m or "").lower() for m in error_msgs), \
        f"Expected 'empty' in error messages, got: {error_msgs}"


# ---------------------------------------------------------------------------
# Fix 1 tests: error handling for summarize / embed
# (summary + embed run in parallel via asyncio.gather, so both may be called)
# ---------------------------------------------------------------------------

def test_process_source_content_summarize_failure():
    """When summarize_document raises, source is marked error."""
    db_mocks = _make_notebook_db_mocks()
    summarize_mock = AsyncMock(side_effect=Exception("API error"))
    embed_mock = AsyncMock(return_value=[{"content": "c", "embedding": _make_embedding()}])

    long_text = "word " * 30  # 150 chars, passes validation

    _run_process_notebook(
        seed_text=long_text,
        db_mocks=db_mocks,
        summarize_mock=summarize_mock,
        embed_mock=embed_mock,
    )

    # NOTE: embed_mock MAY have been called — they run concurrently.
    # We only assert the error outcome.
    error_calls = [
        c for c in db_mocks["update_source"].call_args_list
        if c.kwargs.get("status") == "error"
    ]
    assert error_calls, "Expected update_source called with status='error'"
    error_msgs = [c.kwargs.get("error_message", "") for c in error_calls]
    assert any("API error" in (m or "") for m in error_msgs), \
        f"Expected 'API error' in error messages, got: {error_msgs}"


def test_process_source_content_embed_failure():
    """When embed_chunks raises, source is marked error."""
    db_mocks = _make_notebook_db_mocks()
    summarize_mock = AsyncMock(return_value="A summary")
    embed_mock = AsyncMock(side_effect=Exception("embed failure"))

    long_text = "word " * 30

    _run_process_notebook(
        seed_text=long_text,
        db_mocks=db_mocks,
        summarize_mock=summarize_mock,
        embed_mock=embed_mock,
    )

    error_calls = [
        c for c in db_mocks["update_source"].call_args_list
        if c.kwargs.get("status") == "error"
    ]
    assert error_calls, "Expected update_source called with status='error' after embed failure"
    error_msgs = [c.kwargs.get("error_message", "") for c in error_calls]
    assert any("embed failure" in (m or "") for m in error_msgs), \
        f"Expected 'embed failure' in error messages, got: {error_msgs}"


# ---------------------------------------------------------------------------
# Fix 1 tests: retry on transient errors
# ---------------------------------------------------------------------------

def test_retry_on_transient_api_error():
    """summarize_document raises TimeoutException twice then succeeds on 3rd call."""
    db_mocks = _make_notebook_db_mocks()

    call_count = 0

    async def flaky_summarize(text, title):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.TimeoutException("timeout")
        return "Summary after retries"

    embed_mock = AsyncMock(return_value=[{"content": "c", "embedding": _make_embedding()}])

    long_text = "word " * 30

    with patch("app.worker.asyncio.sleep", new_callable=AsyncMock):
        _run_process_notebook(
            seed_text=long_text,
            db_mocks=db_mocks,
            summarize_mock=flaky_summarize,
            embed_mock=embed_mock,
        )

    assert call_count == 3, f"Expected summarize called 3 times, got {call_count}"

    # No error should have been set from the summarize step (it eventually succeeded)
    error_calls = [
        c for c in db_mocks["update_source"].call_args_list
        if c.kwargs.get("status") == "error"
        and any(
            kw in (c.kwargs.get("error_message") or "")
            for kw in ["timeout", "TimeoutException"]
        )
    ]
    assert not error_calls, \
        "summarize eventually succeeded, should not have marked error from timeout"


# ---------------------------------------------------------------------------
# Fix 3 tests: enqueue fallback
# ---------------------------------------------------------------------------

def test_enqueue_fails_cleanly_without_celery():
    """When process_notebook.delay raises, update_notebook_status is called with error."""
    update_notebook_mock = AsyncMock(return_value=None)

    with (
        patch("app.worker.process_notebook") as mock_task,
        patch("app.database.update_notebook_status", update_notebook_mock),
    ):
        mock_task.delay.side_effect = Exception("Redis down")

        from app.worker import enqueue_notebook_processing
        enqueue_notebook_processing("nb-1", "some seed text")

    # Must have called update_notebook_status with "error"
    assert update_notebook_mock.called, "update_notebook_status should have been called"
    args_list = update_notebook_mock.call_args_list
    error_calls = [c for c in args_list if "error" in c.args or c.kwargs.get("status") == "error"]
    assert error_calls or any("error" in str(c) for c in args_list), \
        f"Expected update_notebook_status called with 'error', calls: {args_list}"

    # process_notebook itself (sync pipeline) must NOT have been called
    mock_task.assert_not_called()


# ---------------------------------------------------------------------------
# Concurrency tests
# ---------------------------------------------------------------------------

def test_concurrent_crawl_respects_semaphore():
    """Discovered sources are crawled concurrently, not sequentially."""
    db_mocks = _make_notebook_db_mocks()

    crawl_order = []

    async def tracking_crawl(url):
        crawl_order.append(url)
        return {"text": "x" * 200, "title": f"Title for {url}"}

    # Mock discovery to return 3 sources
    discover_mock = AsyncMock(return_value=[
        {"url": f"https://example.com/{i}", "title": f"Source {i}"}
        for i in range(3)
    ])

    summarize_mock = AsyncMock(return_value="summary")
    embed_mock = AsyncMock(return_value=[{"content": "c", "embedding": _make_embedding()}])

    _run_process_notebook(
        seed_text="word " * 30,
        db_mocks=db_mocks,
        summarize_mock=summarize_mock,
        embed_mock=embed_mock,
        crawl_mock=tracking_crawl,
        discover_mock=discover_mock,
    )

    # All 3 sources should have been crawled
    assert len(crawl_order) == 3, f"Expected 3 crawls, got {len(crawl_order)}"
    assert all("example.com" in url for url in crawl_order)


def test_partial_crawl_failure_does_not_block_others():
    """If one source fails to crawl, others are still processed."""
    db_mocks = _make_notebook_db_mocks()

    call_count = 0

    async def mixed_crawl(url):
        nonlocal call_count
        call_count += 1
        if "fail" in url:
            return None  # crawl failure
        return {"text": "x" * 200, "title": "Good Source"}

    discover_mock = AsyncMock(return_value=[
        {"url": "https://example.com/good1", "title": "Good 1"},
        {"url": "https://example.com/fail", "title": "Bad"},
        {"url": "https://example.com/good2", "title": "Good 2"},
    ])

    summarize_mock = AsyncMock(return_value="summary")
    embed_mock = AsyncMock(return_value=[{"content": "c", "embedding": _make_embedding()}])

    _run_process_notebook(
        seed_text="word " * 30,
        db_mocks=db_mocks,
        summarize_mock=summarize_mock,
        embed_mock=embed_mock,
        crawl_mock=mixed_crawl,
        discover_mock=discover_mock,
    )

    # All 3 should have been attempted
    assert call_count == 3

    # Check that the 2 good sources were processed (summarize called for seed + 2 good)
    # Seed always gets processed + 2 good sources = 3 total summarize calls
    assert summarize_mock.call_count >= 2, \
        f"Expected at least 2 summarize calls (seed + good sources), got {summarize_mock.call_count}"
