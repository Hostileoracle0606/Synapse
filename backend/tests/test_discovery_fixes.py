from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import discovery
from app.services.discovery import _is_valid_source_url


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gemini_response(urls: list[str]):
    """Build a minimal fake Gemini response carrying grounding chunks."""
    chunks = []
    for url in urls:
        web = MagicMock()
        web.uri = url
        web.title = url
        chunk = MagicMock()
        chunk.web = web
        chunks.append(chunk)

    metadata = MagicMock()
    metadata.grounding_chunks = chunks

    candidate = MagicMock()
    candidate.grounding_metadata = metadata

    response = MagicMock()
    response.candidates = [candidate]
    return response


def _make_fake_client(urls: list[str]):
    """Return a fake Gemini client whose generate_content returns urls."""
    response = _make_gemini_response(urls)
    client = MagicMock()
    client.models.generate_content.return_value = response
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discovery_empty_on_no_gemini(monkeypatch):
    """When Gemini client is None, discover_related_sources returns []."""
    monkeypatch.setattr(discovery, "get_gemini_client", lambda: None)

    results = await discovery.discover_related_sources(
        "Neural networks are transforming healthcare diagnostics.",
        max_results=5,
    )

    assert results == []
    # Double-check no search engine URLs snuck in
    for item in results:
        assert "google.com" not in item.get("url", "")
        assert "scholar" not in item.get("url", "")


@pytest.mark.asyncio
async def test_discovery_filters_google_domain(monkeypatch):
    """google.com URLs are filtered out; valid URLs are kept."""
    urls = [
        "https://www.google.com/search?q=test",
        "https://example.com/article",
    ]
    monkeypatch.setattr(discovery, "get_gemini_client", lambda: _make_fake_client(urls))
    monkeypatch.setattr(
        discovery,
        "get_settings",
        lambda: type("S", (), {"gemini_model": "gemini-pro"})(),
    )
    monkeypatch.setattr(discovery, "types", MagicMock())

    results = await discovery.discover_related_sources("test text", max_results=10)

    returned_urls = [r["url"] for r in results]
    assert "https://www.google.com/search?q=test" not in returned_urls
    assert "https://example.com/article" in returned_urls


@pytest.mark.asyncio
async def test_discovery_filters_social_media(monkeypatch):
    """Social media URLs (twitter.com) are filtered out."""
    urls = ["https://twitter.com/user/status/123"]
    monkeypatch.setattr(discovery, "get_gemini_client", lambda: _make_fake_client(urls))
    monkeypatch.setattr(
        discovery,
        "get_settings",
        lambda: type("S", (), {"gemini_model": "gemini-pro"})(),
    )
    monkeypatch.setattr(discovery, "types", MagicMock())

    results = await discovery.discover_related_sources("test text", max_results=10)

    assert results == []


@pytest.mark.asyncio
async def test_discovery_filters_search_query_urls(monkeypatch):
    """URLs containing /search? are filtered out."""
    urls = ["https://somesite.com/search?q=topic"]
    monkeypatch.setattr(discovery, "get_gemini_client", lambda: _make_fake_client(urls))
    monkeypatch.setattr(
        discovery,
        "get_settings",
        lambda: type("S", (), {"gemini_model": "gemini-pro"})(),
    )
    monkeypatch.setattr(discovery, "types", MagicMock())

    results = await discovery.discover_related_sources("test text", max_results=10)

    assert results == []


@pytest.mark.asyncio
async def test_discovery_keeps_valid_urls(monkeypatch):
    """Valid, non-blocked URLs pass through the filter unchanged."""
    urls = [
        "https://arxiv.org/abs/1234",
        "https://nature.com/articles/xyz",
    ]
    monkeypatch.setattr(discovery, "get_gemini_client", lambda: _make_fake_client(urls))
    monkeypatch.setattr(
        discovery,
        "get_settings",
        lambda: type("S", (), {"gemini_model": "gemini-pro"})(),
    )
    monkeypatch.setattr(discovery, "types", MagicMock())

    results = await discovery.discover_related_sources("test text", max_results=10)

    returned_urls = [r["url"] for r in results]
    assert "https://arxiv.org/abs/1234" in returned_urls
    assert "https://nature.com/articles/xyz" in returned_urls


def test_is_valid_source_url_rejects_non_http():
    """Non-http/https schemes (e.g. ftp) are rejected."""
    assert _is_valid_source_url("ftp://example.com") is False
