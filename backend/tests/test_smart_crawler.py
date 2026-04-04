from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Task 1 — Config fields
# ---------------------------------------------------------------------------

def test_config_has_firecrawl_fields():
    config = importlib.import_module("app.config")
    importlib.reload(config)
    settings = config.Settings()
    assert hasattr(settings, "firecrawl_api_key")
    assert settings.firecrawl_fallback_min_chars == 200


def test_config_firecrawl_fields_overridable(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-key")
    monkeypatch.setenv("FIRECRAWL_FALLBACK_MIN_CHARS", "500")

    config = importlib.import_module("app.config")
    importlib.reload(config)
    settings = config.Settings()

    assert settings.firecrawl_api_key == "fc-test-key"
    assert settings.firecrawl_fallback_min_chars == 500


# ---------------------------------------------------------------------------
# Task 2 — _looks_like_pdf + crawl_url_with_firecrawl
# ---------------------------------------------------------------------------

from app.services import crawler


def test_looks_like_pdf_explicit_source_type():
    from app.services.crawler import _looks_like_pdf
    assert _looks_like_pdf("https://example.com/doc", "pdf") is True


def test_looks_like_pdf_url_extension():
    from app.services.crawler import _looks_like_pdf
    assert _looks_like_pdf("https://example.com/report.pdf", "webpage") is True
    assert _looks_like_pdf("https://example.com/report.pdf?v=1", "webpage") is True


def test_looks_like_pdf_not_pdf():
    from app.services.crawler import _looks_like_pdf
    assert _looks_like_pdf("https://example.com/page.html", "webpage") is False
    assert _looks_like_pdf("https://example.com/report.pdfx", "webpage") is False


@pytest.mark.asyncio
async def test_firecrawl_returns_none_when_no_api_key(monkeypatch):
    monkeypatch.setattr(
        crawler, "get_settings",
        lambda: type("S", (), {"firecrawl_api_key": None, "max_document_chars": 10_000})(),
    )
    result = await crawler.crawl_url_with_firecrawl("https://example.com/doc.pdf")
    assert result is None


@pytest.mark.asyncio
async def test_firecrawl_returns_none_when_package_absent(monkeypatch):
    monkeypatch.setattr(crawler, "AsyncFirecrawlApp", None, raising=False)
    monkeypatch.setattr(
        crawler, "get_settings",
        lambda: type("S", (), {"firecrawl_api_key": "fc-key", "max_document_chars": 10_000})(),
    )
    result = await crawler.crawl_url_with_firecrawl("https://example.com/doc.pdf")
    assert result is None


@pytest.mark.asyncio
async def test_firecrawl_returns_text_and_title(monkeypatch):
    mock_result = MagicMock()
    mock_result.markdown = "# PDF Title\n\nSome extracted content here."
    mock_result.metadata = MagicMock()
    mock_result.metadata.title = "PDF Title"

    mock_app_instance = AsyncMock()
    mock_app_instance.scrape = AsyncMock(return_value=mock_result)

    mock_class = MagicMock(return_value=mock_app_instance)
    monkeypatch.setattr(crawler, "AsyncFirecrawlApp", mock_class)
    monkeypatch.setattr(
        crawler, "get_settings",
        lambda: type("S", (), {"firecrawl_api_key": "fc-test", "max_document_chars": 10_000})(),
    )

    result = await crawler.crawl_url_with_firecrawl("https://example.com/doc.pdf")

    assert result is not None
    assert result["text"] == "# PDF Title\n\nSome extracted content here."
    assert result["title"] == "PDF Title"
    mock_class.assert_called_once_with(api_key="fc-test")
    mock_app_instance.scrape.assert_called_once_with(
        "https://example.com/doc.pdf", formats=["markdown"]
    )


@pytest.mark.asyncio
async def test_firecrawl_returns_none_on_empty_markdown(monkeypatch):
    mock_result = MagicMock()
    mock_result.markdown = None
    mock_result.metadata = MagicMock()
    mock_result.metadata.title = "No Content"

    mock_app_instance = AsyncMock()
    mock_app_instance.scrape = AsyncMock(return_value=mock_result)
    monkeypatch.setattr(crawler, "AsyncFirecrawlApp", MagicMock(return_value=mock_app_instance))
    monkeypatch.setattr(
        crawler, "get_settings",
        lambda: type("S", (), {"firecrawl_api_key": "fc-test", "max_document_chars": 10_000})(),
    )

    result = await crawler.crawl_url_with_firecrawl("https://example.com/doc.pdf")
    assert result is None


@pytest.mark.asyncio
async def test_firecrawl_returns_none_on_sdk_exception(monkeypatch):
    mock_app_instance = AsyncMock()
    mock_app_instance.scrape = AsyncMock(side_effect=RuntimeError("API error"))
    monkeypatch.setattr(crawler, "AsyncFirecrawlApp", MagicMock(return_value=mock_app_instance))
    monkeypatch.setattr(
        crawler, "get_settings",
        lambda: type("S", (), {"firecrawl_api_key": "fc-test", "max_document_chars": 10_000})(),
    )

    result = await crawler.crawl_url_with_firecrawl("https://example.com/doc.pdf")
    assert result is None


# ---------------------------------------------------------------------------
# Task 3 — smart_crawl_url routing
# ---------------------------------------------------------------------------


def _fake_settings(min_chars: int = 200):
    return type("S", (), {"firecrawl_fallback_min_chars": min_chars})()


@pytest.mark.asyncio
async def test_smart_crawl_pdf_url_goes_to_firecrawl_not_httpx(monkeypatch):
    """Spec test 1: PDF URL must reach Firecrawl first; crawl_url must not be called."""
    httpx_called = []

    async def fake_crawl_url(url, timeout=15.0):
        httpx_called.append(url)
        return {"text": "html content", "title": "HTML"}

    async def fake_firecrawl(url):
        return {"text": "# PDF\n\n" + "Content " * 50, "title": "PDF Doc"}

    monkeypatch.setattr(crawler, "crawl_url", fake_crawl_url)
    monkeypatch.setattr(crawler, "crawl_url_with_firecrawl", fake_firecrawl)
    monkeypatch.setattr(crawler, "get_settings", lambda: _fake_settings())

    result = await crawler.smart_crawl_url("https://example.com/report.pdf")

    assert result is not None
    assert result["title"] == "PDF Doc"
    assert httpx_called == [], "crawl_url (httpx) must NOT be called for PDF URLs"


@pytest.mark.asyncio
async def test_smart_crawl_pdf_source_type_goes_to_firecrawl(monkeypatch):
    """Explicit source_type='pdf' routes to Firecrawl even without .pdf extension."""
    httpx_called = []

    async def fake_crawl_url(url, timeout=15.0):
        httpx_called.append(url)
        return {"text": "html content", "title": "HTML"}

    async def fake_firecrawl(url):
        return {"text": "# PDF content\n\n" + "x" * 300, "title": "Uploaded PDF"}

    monkeypatch.setattr(crawler, "crawl_url", fake_crawl_url)
    monkeypatch.setattr(crawler, "crawl_url_with_firecrawl", fake_firecrawl)
    monkeypatch.setattr(crawler, "get_settings", lambda: _fake_settings())

    result = await crawler.smart_crawl_url("https://cdn.example.com/file?id=123", source_type="pdf")

    assert result is not None
    assert httpx_called == []


@pytest.mark.asyncio
async def test_smart_crawl_pdf_returns_none_when_firecrawl_fails(monkeypatch):
    """If Firecrawl fails for a PDF, return None (no httpx fallback)."""
    async def fake_crawl_url(url, timeout=15.0):
        return {"text": "this should never be returned", "title": "HTML"}

    async def fake_firecrawl(url):
        return None

    monkeypatch.setattr(crawler, "crawl_url", fake_crawl_url)
    monkeypatch.setattr(crawler, "crawl_url_with_firecrawl", fake_firecrawl)
    monkeypatch.setattr(crawler, "get_settings", lambda: _fake_settings())

    result = await crawler.smart_crawl_url("https://example.com/doc.pdf")
    assert result is None


@pytest.mark.asyncio
async def test_smart_crawl_webpage_uses_httpx_primary(monkeypatch):
    """Normal webpages go through httpx first."""
    httpx_called = []
    long_text = "Content " * 30  # 240 chars, above 200 threshold

    async def fake_crawl_url(url, timeout=15.0):
        httpx_called.append(url)
        return {"text": long_text, "title": "Good Page"}

    async def fake_firecrawl(url):
        return {"text": "Firecrawl should not be called", "title": "FC"}

    monkeypatch.setattr(crawler, "crawl_url", fake_crawl_url)
    monkeypatch.setattr(crawler, "crawl_url_with_firecrawl", fake_firecrawl)
    monkeypatch.setattr(crawler, "get_settings", lambda: _fake_settings())

    result = await crawler.smart_crawl_url("https://example.com/page")

    assert result is not None
    assert result["text"] == long_text
    assert httpx_called == ["https://example.com/page"]


@pytest.mark.asyncio
async def test_smart_crawl_fallback_on_none_primary(monkeypatch):
    """crawl_url returning None triggers Firecrawl fallback."""
    async def fake_crawl_url(url, timeout=15.0):
        return None

    async def fake_firecrawl(url):
        return {"text": "Firecrawl rescued this page. " * 10, "title": "FC Result"}

    monkeypatch.setattr(crawler, "crawl_url", fake_crawl_url)
    monkeypatch.setattr(crawler, "crawl_url_with_firecrawl", fake_firecrawl)
    monkeypatch.setattr(crawler, "get_settings", lambda: _fake_settings())

    result = await crawler.smart_crawl_url("https://example.com/js-heavy")

    assert result is not None
    assert "Firecrawl rescued" in result["text"]


@pytest.mark.asyncio
async def test_smart_crawl_fallback_on_error_dict(monkeypatch):
    """crawl_url returning an error dict triggers Firecrawl fallback."""
    async def fake_crawl_url(url, timeout=15.0):
        return {"url": url, "title": "", "content": "", "error": "Content extraction failed"}

    async def fake_firecrawl(url):
        return {"text": "Firecrawl markdown output. " * 10, "title": "Rescued"}

    monkeypatch.setattr(crawler, "crawl_url", fake_crawl_url)
    monkeypatch.setattr(crawler, "crawl_url_with_firecrawl", fake_firecrawl)
    monkeypatch.setattr(crawler, "get_settings", lambda: _fake_settings())

    result = await crawler.smart_crawl_url("https://example.com/page")

    assert result is not None
    assert result["title"] == "Rescued"


@pytest.mark.asyncio
async def test_smart_crawl_fallback_on_weak_text(monkeypatch):
    """crawl_url returning text shorter than threshold triggers Firecrawl."""
    weak_text = "x" * 80  # below 200-char threshold

    async def fake_crawl_url(url, timeout=15.0):
        return {"text": weak_text, "title": "Weak"}

    async def fake_firecrawl(url):
        return {"text": "Full content from Firecrawl. " * 20, "title": "Full"}

    monkeypatch.setattr(crawler, "crawl_url", fake_crawl_url)
    monkeypatch.setattr(crawler, "crawl_url_with_firecrawl", fake_firecrawl)
    monkeypatch.setattr(crawler, "get_settings", lambda: _fake_settings())

    result = await crawler.smart_crawl_url("https://example.com/thin-page")

    assert result is not None
    assert "Firecrawl" in result["text"]


@pytest.mark.asyncio
async def test_smart_crawl_weak_primary_firecrawl_absent_returns_weak(monkeypatch):
    """Spec test 2: if Firecrawl is unavailable, return weak primary result (not None)."""
    weak_text = "X" * 80

    async def fake_crawl_url(url, timeout=15.0):
        return {"text": weak_text, "title": "Weak"}

    monkeypatch.setattr(crawler, "crawl_url", fake_crawl_url)
    monkeypatch.setattr(crawler, "AsyncFirecrawlApp", None, raising=False)
    monkeypatch.setattr(crawler, "get_settings", lambda: _fake_settings())

    result = await crawler.smart_crawl_url("https://example.com/page")

    assert result is not None
    assert result["text"] == weak_text  # weak result returned, not None


@pytest.mark.asyncio
async def test_smart_crawl_both_fail_returns_none(monkeypatch):
    """If both httpx and Firecrawl return None, smart_crawl_url returns None."""
    async def fake_crawl_url(url, timeout=15.0):
        return None

    async def fake_firecrawl(url):
        return None

    monkeypatch.setattr(crawler, "crawl_url", fake_crawl_url)
    monkeypatch.setattr(crawler, "crawl_url_with_firecrawl", fake_firecrawl)
    monkeypatch.setattr(crawler, "get_settings", lambda: _fake_settings())

    result = await crawler.smart_crawl_url("https://example.com/broken")
    assert result is None


@pytest.mark.asyncio
async def test_smart_crawl_result_never_contains_error_key(monkeypatch):
    """smart_crawl_url must never return a dict with an 'error' key."""
    async def fake_crawl_url(url, timeout=15.0):
        return {"text": "Good content. " * 20, "title": "Page"}

    async def fake_firecrawl(url):
        return None

    monkeypatch.setattr(crawler, "crawl_url", fake_crawl_url)
    monkeypatch.setattr(crawler, "crawl_url_with_firecrawl", fake_firecrawl)
    monkeypatch.setattr(crawler, "get_settings", lambda: _fake_settings())

    result = await crawler.smart_crawl_url("https://example.com/page")

    assert result is not None
    assert "error" not in result
    assert "text" in result
    assert "title" in result


# ---------------------------------------------------------------------------
# Task 4 — Router call site (seed PDF test)
# ---------------------------------------------------------------------------


def test_create_notebook_seed_pdf_no_keyerror(monkeypatch):
    """Spec test 1 (router): seed_url ending in .pdf must not cause KeyError."""
    import sys
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers import notebooks

    smart_crawl_called = []

    async def fake_smart_crawl(url, source_type="webpage"):
        smart_crawl_called.append((url, source_type))
        return {"text": "# Annual Report\n\n" + "Content. " * 100, "title": "Annual Report 2024"}

    async def fake_create_notebook(title, seed_url=None, seed_text=None):
        return {"id": "nb-pdf-1", "title": title, "status": "discovering"}

    def fake_enqueue(notebook_id, seed_text):
        pass

    async def fake_extract_seed_title(text):
        return "Annual Report 2024"

    monkeypatch.setattr(notebooks, "smart_crawl_url", fake_smart_crawl)
    monkeypatch.setattr(notebooks, "create_notebook", fake_create_notebook)
    monkeypatch.setattr(notebooks, "enqueue_notebook_processing", fake_enqueue)
    monkeypatch.setattr(notebooks, "extract_seed_title", fake_extract_seed_title)

    client = TestClient(app)
    response = client.post("/api/notebooks", json={"seed_url": "https://example.com/report.pdf"})

    assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
    data = response.json()
    assert "id" in data
    assert len(smart_crawl_called) == 1
    assert smart_crawl_called[0][0] == "https://example.com/report.pdf"
