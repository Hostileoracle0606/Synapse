from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import crawler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_client(
    head_content_type: str | None = "text/html",
    head_raises: Exception | None = None,
    get_html: str = "",
    get_raises: Exception | None = None,
):
    """Return a FakeClient class whose HEAD/GET behaviour is configurable."""

    class FakeResponse:
        def __init__(self, text: str = "", content_type: str = "text/html"):
            self.text = text
            self.headers = {"content-type": content_type} if content_type else {}

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def head(self, url):
            if head_raises is not None:
                raise head_raises
            ct = head_content_type if head_content_type is not None else ""
            return FakeResponse(content_type=ct)

        async def get(self, url):
            if get_raises is not None:
                raise get_raises
            return FakeResponse(text=get_html, content_type="text/html")

    return FakeClient


# ---------------------------------------------------------------------------
# Fix 1 tests — HTML fallback strips tags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crawler_fallback_strips_html(monkeypatch):
    """Fallback should return plain text with no HTML tags when trafilatura returns None."""
    html = (
        "<html><head><script>alert('x')</script><style>body{}</style></head>"
        "<body><p>Valid content that is long enough to pass the minimum threshold "
        "check for the fallback</p></body></html>"
    )

    FakeClient = _make_fake_client(head_content_type="text/html", get_html=html)

    monkeypatch.setattr(crawler, "trafilatura", None, raising=False)
    monkeypatch.setattr(crawler.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(
        crawler,
        "get_settings",
        lambda: type("S", (), {"max_document_chars": 10_000})(),
    )

    result = await crawler.crawl_url("https://example.com")

    assert result is not None
    assert "text" in result
    content = result["text"]

    # Must contain the paragraph text
    assert "Valid content that is long enough" in content

    # Must not contain any HTML tags
    assert "<" not in content
    assert ">" not in content

    # Must not contain script/style content
    assert "alert" not in content
    assert "body{}" not in content


@pytest.mark.asyncio
async def test_crawler_fallback_too_short_after_strip(monkeypatch):
    """When stripped HTML is <50 chars, return structured failure result."""
    html = "<html><body><p>Short</p></body></html>"

    FakeClient = _make_fake_client(head_content_type="text/html", get_html=html)

    monkeypatch.setattr(crawler, "trafilatura", None, raising=False)
    monkeypatch.setattr(crawler.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(
        crawler,
        "get_settings",
        lambda: type("S", (), {"max_document_chars": 10_000})(),
    )

    result = await crawler.crawl_url("https://example.com")

    assert result is not None
    assert result.get("content") == "" or result.get("text", "nope") == "nope"
    assert result.get("error") == "Content extraction failed"


# ---------------------------------------------------------------------------
# Fix 2 tests — Content-Type guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crawler_skips_non_text_content_type(monkeypatch):
    """image/png HEAD response must cause an immediate failure without a GET."""
    get_called = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def head(self, url):
            class R:
                headers = {"content-type": "image/png"}

                def raise_for_status(self):
                    pass

            return R()

        async def get(self, url):
            get_called.append(url)

            class R:
                text = "<html><body>Should not be fetched</body></html>"
                headers = {}

                def raise_for_status(self):
                    pass

            return R()

    monkeypatch.setattr(crawler.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(
        crawler,
        "get_settings",
        lambda: type("S", (), {"max_document_chars": 10_000})(),
    )

    result = await crawler.crawl_url("https://example.com/image.png")

    assert result is not None
    assert result.get("error") == "Content extraction failed"
    assert get_called == [], "GET must NOT be called for image/* content type"


@pytest.mark.asyncio
async def test_crawler_skips_pdf_content_type(monkeypatch):
    """application/pdf HEAD response must cause immediate failure without GET."""
    get_called = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def head(self, url):
            class R:
                headers = {"content-type": "application/pdf"}

                def raise_for_status(self):
                    pass

            return R()

        async def get(self, url):
            get_called.append(url)

            class R:
                text = "<html><body>Should not be fetched</body></html>"
                headers = {}

                def raise_for_status(self):
                    pass

            return R()

    monkeypatch.setattr(crawler.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(
        crawler,
        "get_settings",
        lambda: type("S", (), {"max_document_chars": 10_000})(),
    )

    result = await crawler.crawl_url("https://example.com/doc.pdf")

    assert result is not None
    assert result.get("error") == "Content extraction failed"
    assert get_called == [], "GET must NOT be called for application/pdf content type"


@pytest.mark.asyncio
async def test_crawler_proceeds_on_text_html(monkeypatch):
    """text/html HEAD response should proceed to full fetch and extract content."""
    long_text = "This is a sufficiently long paragraph of content. " * 5
    html = f"<html><body><p>{long_text}</p></body></html>"

    # Mock trafilatura to return the long text so we don't hit the fallback.
    fake_trafilatura = MagicMock()
    fake_trafilatura.extract.return_value = long_text

    FakeClient = _make_fake_client(head_content_type="text/html", get_html=html)

    monkeypatch.setattr(crawler, "trafilatura", fake_trafilatura, raising=False)
    monkeypatch.setattr(crawler.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(
        crawler,
        "get_settings",
        lambda: type("S", (), {"max_document_chars": 10_000})(),
    )

    result = await crawler.crawl_url("https://example.com")

    assert result is not None
    assert "text" in result
    assert long_text[:50] in result["text"]
    assert result.get("error") is None


@pytest.mark.asyncio
async def test_crawler_proceeds_when_head_fails(monkeypatch):
    """If the HEAD request raises an exception, fall back to full GET without crashing."""
    import httpx as _httpx

    long_text = "This is a sufficiently long paragraph of content. " * 5
    html = f"<html><body><p>{long_text}</p></body></html>"

    fake_trafilatura = MagicMock()
    fake_trafilatura.extract.return_value = long_text

    FakeClient = _make_fake_client(
        head_raises=_httpx.ConnectError("no route"),
        get_html=html,
    )

    monkeypatch.setattr(crawler, "trafilatura", fake_trafilatura, raising=False)
    monkeypatch.setattr(crawler.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(
        crawler,
        "get_settings",
        lambda: type("S", (), {"max_document_chars": 10_000})(),
    )

    result = await crawler.crawl_url("https://example.com")

    # Should succeed — HEAD failure must not crash the crawler.
    assert result is not None
    assert "text" in result
    assert result.get("error") is None
