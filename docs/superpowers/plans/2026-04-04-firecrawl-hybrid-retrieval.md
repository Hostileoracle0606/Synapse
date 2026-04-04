# Firecrawl Integration + Hybrid Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken PDF crawl path with Firecrawl and replace vector-only chunk retrieval with Supabase FTS + pgvector + RRF fusion.

**Architecture:** A `smart_crawl_url()` wrapper in `crawler.py` routes by source type and falls back to Firecrawl when the primary extraction is weak or fails. A Supabase RPC `hybrid_search_chunks` fuses lexical and vector scores with RRF in SQL; `rag.py` calls it and applies per-source grouping in Python.

**Tech Stack:** Python 3.11+, FastAPI, `firecrawl-py` (AsyncFirecrawlApp), Supabase pgvector (`vector(768)`), Postgres `tsvector` + GIN index, pytest + pytest-asyncio

---

## File Map

| Action | File | What changes |
|---|---|---|
| Modify | `backend/requirements.txt` | Add `firecrawl-py` |
| Modify | `backend/app/config.py` | 2 new fields |
| Modify | `backend/app/services/crawler.py` | Optional FC import, `_looks_like_pdf`, `crawl_url_with_firecrawl`, `smart_crawl_url` |
| Modify | `backend/app/routers/notebooks.py` | Swap import + call site |
| Modify | `backend/app/worker.py` | Swap import + call site |
| Modify | `backend/app/database.py` | `hybrid_search_chunks` on both repos + module-level |
| Modify | `backend/app/services/rag.py` | `_coerce_and_score_chunks` helper, refactored `retrieve_relevant_sources` |
| Create | `backend/migrations/add_source_chunks_fts.sql` | ALTER TABLE + GIN index |
| Create | `backend/migrations/rpc_hybrid_search_chunks.sql` | Supabase RPC definition |
| Modify | `backend/supabase_schema.sql` | Append migration + RPC for documentation |
| Create | `backend/tests/test_smart_crawler.py` | All Firecrawl + smart routing tests |
| Create | `backend/tests/test_hybrid_retrieval.py` | All hybrid retrieval tests |
| Modify | `backend/tests/test_routers.py` | Update patched name: `crawl_url` → `smart_crawl_url` |

All test commands run from `backend/`. The project has no git repo, so commit steps are omitted.

---

## Part A — Firecrawl Integration

---

### Task 1: Config fields + dependency

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/requirements.txt`
- Create: `backend/tests/test_smart_crawler.py`

- [ ] **Step 1: Write the failing config test**

Create `backend/tests/test_smart_crawler.py`:

```python
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
    assert settings.firecrawl_api_key is None       # no env var set
    assert settings.firecrawl_fallback_min_chars == 200


def test_config_firecrawl_fields_overridable(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-key")
    monkeypatch.setenv("FIRECRAWL_FALLBACK_MIN_CHARS", "500")

    config = importlib.import_module("app.config")
    importlib.reload(config)
    settings = config.Settings()

    assert settings.firecrawl_api_key == "fc-test-key"
    assert settings.firecrawl_fallback_min_chars == 500
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
cd /Users/trinabgoswamy/Synapse/backend
python -m pytest tests/test_smart_crawler.py::test_config_has_firecrawl_fields -v
```
Expected: `AttributeError: type object 'Settings' has no attribute 'firecrawl_api_key'`

- [ ] **Step 3: Add config fields**

In `backend/app/config.py`, add after the `supabase_key` line:

```python
    firecrawl_api_key: Optional[str] = os.getenv("FIRECRAWL_API_KEY")
    firecrawl_fallback_min_chars: int = int(os.getenv("FIRECRAWL_FALLBACK_MIN_CHARS", "200"))
```

The full Settings dataclass should look like:

```python
@dataclass(frozen=True)
class Settings:
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    supabase_url: Optional[str] = os.getenv("SUPABASE_URL")
    supabase_key: Optional[str] = os.getenv("SUPABASE_KEY")
    firecrawl_api_key: Optional[str] = os.getenv("FIRECRAWL_API_KEY")
    firecrawl_fallback_min_chars: int = int(os.getenv("FIRECRAWL_FALLBACK_MIN_CHARS", "200"))
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    # ... rest unchanged
```

- [ ] **Step 4: Add `firecrawl-py` to requirements**

In `backend/requirements.txt`, add on a new line:
```
firecrawl-py>=1.4.0
```

- [ ] **Step 5: Run to confirm PASS**

```bash
python -m pytest tests/test_smart_crawler.py::test_config_has_firecrawl_fields tests/test_smart_crawler.py::test_config_firecrawl_fields_overridable -v
```
Expected: both PASS

- [ ] **Step 6: Confirm existing config tests still pass**

```bash
python -m pytest tests/test_config_rag_fixes.py tests/test_config.py -v
```
Expected: all PASS

---

### Task 2: `_looks_like_pdf` + `crawl_url_with_firecrawl`

**Files:**
- Modify: `backend/app/services/crawler.py`
- Modify: `backend/tests/test_smart_crawler.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_smart_crawler.py`:

```python
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
    mock_app_instance.scrape_url = AsyncMock(return_value=mock_result)

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
    mock_app_instance.scrape_url.assert_called_once_with(
        "https://example.com/doc.pdf", formats=["markdown"]
    )


@pytest.mark.asyncio
async def test_firecrawl_returns_none_on_empty_markdown(monkeypatch):
    mock_result = MagicMock()
    mock_result.markdown = None
    mock_result.metadata = MagicMock()
    mock_result.metadata.title = "No Content"

    mock_app_instance = AsyncMock()
    mock_app_instance.scrape_url = AsyncMock(return_value=mock_result)
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
    mock_app_instance.scrape_url = AsyncMock(side_effect=RuntimeError("API error"))
    monkeypatch.setattr(crawler, "AsyncFirecrawlApp", MagicMock(return_value=mock_app_instance))
    monkeypatch.setattr(
        crawler, "get_settings",
        lambda: type("S", (), {"firecrawl_api_key": "fc-test", "max_document_chars": 10_000})(),
    )

    result = await crawler.crawl_url_with_firecrawl("https://example.com/doc.pdf")
    assert result is None
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
python -m pytest tests/test_smart_crawler.py -k "looks_like_pdf or firecrawl" -v
```
Expected: `ImportError` or `AttributeError` — functions don't exist yet

- [ ] **Step 3: Add optional import + two functions to `crawler.py`**

At the top of `backend/app/services/crawler.py`, after the `trafilatura` try/except block, add:

```python
try:
    from firecrawl import AsyncFirecrawlApp
except Exception:  # pragma: no cover - optional dependency
    AsyncFirecrawlApp = None  # type: ignore[assignment,misc]
```

After the `_failure_result` function (around line 72), add:

```python
def _looks_like_pdf(url: str, source_type: str) -> bool:
    """Return True when the URL or explicit source_type indicates a PDF."""
    return source_type == "pdf" or url.lower().split("?")[0].endswith(".pdf")


async def crawl_url_with_firecrawl(url: str) -> dict[str, str] | None:
    """Fetch *url* via the Firecrawl API and return ``{"text": ..., "title": ...}``.

    Returns None if Firecrawl is unavailable, the key is unset, the result is
    empty, or any exception is raised.

    Note: scrape_url is the current SDK method name; verify against the pinned
    firecrawl-py version if upgrading past the 1.x line.
    """
    settings = get_settings()
    if AsyncFirecrawlApp is None or not settings.firecrawl_api_key:
        return None
    try:
        app = AsyncFirecrawlApp(api_key=settings.firecrawl_api_key)
        result = await app.scrape_url(url, formats=["markdown"])
        markdown = getattr(result, "markdown", None)
        if not markdown:
            return None
        metadata = getattr(result, "metadata", None)
        title = (getattr(metadata, "title", None) if metadata else None) or url
        return {"text": markdown[: settings.max_document_chars], "title": title}
    except Exception as exc:
        logger.warning("Firecrawl failed for %s: %s", url, exc)
        return None
```

- [ ] **Step 4: Run to confirm PASS**

```bash
python -m pytest tests/test_smart_crawler.py -k "looks_like_pdf or firecrawl" -v
```
Expected: all PASS

- [ ] **Step 5: Confirm no regressions**

```bash
python -m pytest tests/test_crawler_fixes.py -v
```
Expected: all PASS

---

### Task 3: `smart_crawl_url` routing

**Files:**
- Modify: `backend/app/services/crawler.py`
- Modify: `backend/tests/test_smart_crawler.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_smart_crawler.py`:

```python
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
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
python -m pytest tests/test_smart_crawler.py -k "smart_crawl" -v
```
Expected: `AttributeError: module 'app.services.crawler' has no attribute 'smart_crawl_url'`

- [ ] **Step 3: Add `smart_crawl_url` to `crawler.py`**

Append after `crawl_url_with_firecrawl`:

```python
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
```

- [ ] **Step 4: Run to confirm PASS**

```bash
python -m pytest tests/test_smart_crawler.py -v
```
Expected: all PASS

- [ ] **Step 5: Confirm no regressions in existing crawler tests**

```bash
python -m pytest tests/test_crawler_fixes.py -v
```
Expected: all PASS

---

### Task 4: Update call sites + fix broken existing test

**Files:**
- Modify: `backend/app/routers/notebooks.py`
- Modify: `backend/app/worker.py`
- Modify: `backend/tests/test_routers.py`

- [ ] **Step 1: Write the seed-PDF router test**

Append to `backend/tests/test_smart_crawler.py`:

```python
# ---------------------------------------------------------------------------
# Task 4 — Router call site (seed PDF test)
# ---------------------------------------------------------------------------


def test_create_notebook_seed_pdf_no_keyerror(monkeypatch):
    """Spec test 1 (router): seed_url ending in .pdf must not cause KeyError."""
    import sys
    from fastapi.testclient import TestClient

    # Must import after sys.path is set (conftest does this)
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
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
python -m pytest tests/test_smart_crawler.py::test_create_notebook_seed_pdf_no_keyerror -v
```
Expected: FAIL — `notebooks` module still imports `crawl_url` not `smart_crawl_url`

- [ ] **Step 3: Update `notebooks.py`**

In `backend/app/routers/notebooks.py`, change line 12:
```python
# Before:
from app.services.crawler import crawl_url

# After:
from app.services.crawler import smart_crawl_url
```

Change line 24:
```python
# Before:
        crawled = await crawl_url(req.seed_url)

# After:
        crawled = await smart_crawl_url(req.seed_url)
```

The full function after the change:
```python
@router.post("", response_model=NotebookCreateResponse)
async def create_notebook_endpoint(req: CreateNotebookRequest):
    seed_text = req.seed_text
    title = req.title

    if req.seed_url:
        crawled = await smart_crawl_url(req.seed_url)
        if not crawled:
            raise HTTPException(status_code=400, detail="Could not fetch the provided URL")
        seed_text = crawled["text"]
        title = title or crawled["title"]
    elif not seed_text:
        raise HTTPException(status_code=400, detail="Provide seed_url or seed_text")

    title = title or await extract_seed_title(seed_text or "")
    notebook = await create_notebook(title=title, seed_url=req.seed_url, seed_text=seed_text)
    enqueue_notebook_processing(notebook["id"], seed_text or "")

    return NotebookCreateResponse(
        id=notebook["id"],
        title=notebook["title"],
        status=notebook["status"],
    )
```

- [ ] **Step 4: Update `worker.py`**

In `backend/app/worker.py`, change line 172 inside `_process_notebook_async`:
```python
# Before:
    from app.services.crawler import crawl_url

# After:
    from app.services.crawler import smart_crawl_url
```

Change line 222 inside `_crawl_one`:
```python
# Before:
                crawled = await crawl_url(record["url"])

# After:
                crawled = await smart_crawl_url(record["url"], record.get("source_type", "webpage"))
```

- [ ] **Step 5: Fix the broken existing router test**

In `backend/tests/test_routers.py`, find `test_create_notebook_from_url_failure` and change:
```python
# Before:
def test_create_notebook_from_url_failure(monkeypatch):
    async def fake_crawl_url(url):
        return None

    monkeypatch.setattr(notebooks, "crawl_url", fake_crawl_url)

# After:
def test_create_notebook_from_url_failure(monkeypatch):
    async def fake_smart_crawl(url, source_type="webpage"):
        return None

    monkeypatch.setattr(notebooks, "smart_crawl_url", fake_smart_crawl)
```

- [ ] **Step 6: Run all related tests**

```bash
python -m pytest tests/test_smart_crawler.py tests/test_routers.py tests/test_crawler_fixes.py -v
```
Expected: all PASS

---

## Part B — Hybrid Retrieval

---

### Task 5: Supabase migration SQL

**Files:**
- Create: `backend/migrations/add_source_chunks_fts.sql`
- Modify: `backend/supabase_schema.sql`

- [ ] **Step 1: Create the migrations directory and migration file**

```bash
mkdir -p /Users/trinabgoswamy/Synapse/backend/migrations
```

Create `backend/migrations/add_source_chunks_fts.sql`:

```sql
-- Migration: add tsvector FTS column + GIN index to source_chunks
-- Apply in Supabase Dashboard → SQL Editor, then run rpc_hybrid_search_chunks.sql

ALTER TABLE source_chunks
  ADD COLUMN IF NOT EXISTS fts tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

CREATE INDEX IF NOT EXISTS source_chunks_fts_idx
  ON source_chunks USING GIN(fts);
```

- [ ] **Step 2: Append to `supabase_schema.sql` for documentation**

At the end of `backend/supabase_schema.sql`, append:

```sql
-- Migration 2026-04-04: FTS column for hybrid retrieval
-- Run backend/migrations/add_source_chunks_fts.sql then
-- backend/migrations/rpc_hybrid_search_chunks.sql in Supabase SQL Editor.
alter table source_chunks
  add column if not exists fts tsvector
    generated always as (to_tsvector('english', content)) stored;

create index if not exists source_chunks_fts_idx
  on source_chunks using gin(fts);
```

- [ ] **Step 3: Apply the migration in Supabase**

Go to your Supabase project → SQL Editor → New query.
Paste and run the contents of `backend/migrations/add_source_chunks_fts.sql`.

Expected: `ALTER TABLE` and `CREATE INDEX` succeed with no errors.
If you see "column already exists", the migration was already applied — safe to ignore.

---

### Task 6: `hybrid_search_chunks` RPC

**Files:**
- Create: `backend/migrations/rpc_hybrid_search_chunks.sql`
- Modify: `backend/supabase_schema.sql`

- [ ] **Step 1: Create the RPC SQL file**

Create `backend/migrations/rpc_hybrid_search_chunks.sql`:

```sql
-- RPC: hybrid_search_chunks
-- Fuses pgvector ANN search with Postgres full-text search using RRF.
-- Requires: source_chunks.fts tsvector column (add_source_chunks_fts.sql)
-- Apply in Supabase Dashboard → SQL Editor.

CREATE OR REPLACE FUNCTION hybrid_search_chunks(
  p_notebook_id     uuid,
  p_query_text      text,
  p_query_embedding vector(768),
  p_match_count     int DEFAULT 10,
  p_rrf_k           int DEFAULT 60
)
RETURNS TABLE(source_id uuid, content text, chunk_index int, rrf_score float8)
LANGUAGE sql STABLE
AS $$
  WITH
    tsq AS (
      SELECT websearch_to_tsquery('english', p_query_text) AS q
    ),
    vec_ranked AS (
      SELECT
        sc.source_id,
        sc.content,
        sc.chunk_index,
        ROW_NUMBER() OVER (ORDER BY sc.embedding <=> p_query_embedding) AS rank
      FROM source_chunks sc
      WHERE sc.notebook_id = p_notebook_id
      ORDER BY sc.embedding <=> p_query_embedding
      LIMIT GREATEST(p_match_count * 3, 20)
    ),
    fts_ranked AS (
      SELECT
        sc.source_id,
        sc.content,
        sc.chunk_index,
        ROW_NUMBER() OVER (
          ORDER BY ts_rank_cd(sc.fts, (SELECT q FROM tsq)) DESC
        ) AS rank
      FROM source_chunks sc
      WHERE sc.notebook_id = p_notebook_id
        AND (SELECT q FROM tsq) IS NOT NULL
        AND sc.fts @@ (SELECT q FROM tsq)
      ORDER BY ts_rank_cd(sc.fts, (SELECT q FROM tsq)) DESC
      LIMIT GREATEST(p_match_count * 3, 20)
    )
  SELECT
    COALESCE(v.source_id,    f.source_id)    AS source_id,
    COALESCE(v.content,      f.content)      AS content,
    COALESCE(v.chunk_index,  f.chunk_index)  AS chunk_index,
    COALESCE(1.0 / (p_rrf_k + v.rank), 0.0)
      + COALESCE(1.0 / (p_rrf_k + f.rank), 0.0)  AS rrf_score
  FROM vec_ranked v
  FULL OUTER JOIN fts_ranked f
    ON v.source_id = f.source_id
   AND v.chunk_index = f.chunk_index
  ORDER BY rrf_score DESC
  LIMIT p_match_count;
$$;
```

- [ ] **Step 2: Append to `supabase_schema.sql`**

At the end of `backend/supabase_schema.sql`, after the FTS column block you added in Task 5, append:

```sql
-- RPC for hybrid retrieval (see backend/migrations/rpc_hybrid_search_chunks.sql)
-- Abbreviated here; run the full file from Supabase SQL Editor.
```

- [ ] **Step 3: Apply the RPC in Supabase**

Go to Supabase → SQL Editor → New query.
Paste and run the full contents of `backend/migrations/rpc_hybrid_search_chunks.sql`.

Expected: `CREATE FUNCTION` with no errors.
Verify in Supabase → Database → Functions: `hybrid_search_chunks` should appear.

---

### Task 7: `hybrid_search_chunks` in `database.py`

**Files:**
- Modify: `backend/app/database.py`
- Create: `backend/tests/test_hybrid_retrieval.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_hybrid_retrieval.py`:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Task 7 — hybrid_search_chunks in database.py
# ---------------------------------------------------------------------------


def _make_in_memory_repo_with_chunks():
    """Return a populated InMemoryRepository with one notebook, source, and two chunks."""
    from app.database import InMemoryRepository

    repo = InMemoryRepository()
    notebook = repo.create_notebook("test-nb", seed_text="seed")
    source = repo.create_source(notebook["id"], "http://example.com", "Test Source")
    repo.replace_source_chunks(source["id"], notebook["id"], [
        {
            "chunk_index": 0,
            "content": "neural networks deep learning",
            "char_start": 0,
            "char_end": 29,
            "embedding": [1.0, 0.0],
        },
        {
            "chunk_index": 1,
            "content": "quantum physics and thermodynamics",
            "char_start": 29,
            "char_end": 63,
            "embedding": [0.0, 1.0],
        },
    ])
    return repo, notebook["id"], source["id"]


def test_in_memory_hybrid_search_returns_top_result_first():
    """InMemoryRepository.hybrid_search_chunks scores by cosine and ranks correctly."""
    repo, notebook_id, _ = _make_in_memory_repo_with_chunks()

    # Query embedding similar to chunk 0 ([1,0])
    results = repo.hybrid_search_chunks(notebook_id, "neural", [1.0, 0.0], match_count=5)

    assert len(results) >= 1
    assert results[0]["content"] == "neural networks deep learning"
    assert "rrf_score" in results[0]
    assert results[0]["rrf_score"] >= results[-1]["rrf_score"]


def test_in_memory_hybrid_search_respects_match_count():
    repo, notebook_id, _ = _make_in_memory_repo_with_chunks()
    results = repo.hybrid_search_chunks(notebook_id, "any query", [1.0, 0.0], match_count=1)
    assert len(results) == 1


def test_in_memory_hybrid_search_wrong_notebook_returns_empty():
    repo, _, _ = _make_in_memory_repo_with_chunks()
    results = repo.hybrid_search_chunks("nonexistent-nb", "neural", [1.0, 0.0], match_count=5)
    assert results == []


@pytest.mark.asyncio
async def test_module_level_hybrid_search_delegates_to_repo(monkeypatch):
    """Module-level hybrid_search_chunks delegates to the active repository."""
    import app.database as db_module

    mock_repo = MagicMock()
    mock_repo.hybrid_search_chunks.return_value = [
        {"source_id": "s1", "content": "chunk text", "chunk_index": 0, "rrf_score": 0.9}
    ]
    monkeypatch.setattr(db_module, "_repository", mock_repo)

    result = await db_module.hybrid_search_chunks("nb-1", "query text", [1.0, 0.0], 10)

    assert result == [{"source_id": "s1", "content": "chunk text", "chunk_index": 0, "rrf_score": 0.9}]
    mock_repo.hybrid_search_chunks.assert_called_once_with("nb-1", "query text", [1.0, 0.0], 10)
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
cd /Users/trinabgoswamy/Synapse/backend
python -m pytest tests/test_hybrid_retrieval.py -k "hybrid_search" -v
```
Expected: `AttributeError: 'InMemoryRepository' object has no attribute 'hybrid_search_chunks'`

- [ ] **Step 3: Add `hybrid_search_chunks` to `InMemoryRepository`**

In `backend/app/database.py`, inside the `InMemoryRepository` class, add after `get_notebook_chunks`:

```python
    def hybrid_search_chunks(
        self,
        notebook_id: str,
        query_text: str,
        query_embedding: list[float],
        match_count: int,
    ) -> list[dict[str, Any]]:
        """Vector-only cosine fallback — no FTS available in memory."""
        from app.services.graph import cosine_similarity

        with self._lock:
            chunks = [
                chunk for chunk in self._source_chunks.values()
                if chunk["notebook_id"] == notebook_id
            ]

        scored: list[dict[str, Any]] = []
        for chunk in chunks:
            raw = chunk.get("embedding") or []
            emb = [float(v) for v in raw]
            score = cosine_similarity(query_embedding, emb)
            scored.append({**deepcopy(chunk), "rrf_score": score})

        scored.sort(key=lambda c: c["rrf_score"], reverse=True)
        return scored[:match_count]
```

- [ ] **Step 4: Add `hybrid_search_chunks` to `SupabaseRepository`**

Inside `SupabaseRepository`, add after `get_notebook_chunks`:

```python
    def hybrid_search_chunks(
        self,
        notebook_id: str,
        query_text: str,
        query_embedding: list[float],
        match_count: int,
    ) -> list[dict[str, Any]]:
        result = self._client.rpc(
            "hybrid_search_chunks",
            {
                "p_notebook_id": notebook_id,
                "p_query_text": query_text,
                "p_query_embedding": query_embedding,
                "p_match_count": match_count,
            },
        ).execute()
        return result.data
```

- [ ] **Step 5: Add module-level `hybrid_search_chunks` function**

In `backend/app/database.py`, after the `get_notebook_chunks` module-level function (around line 541), add:

```python
async def hybrid_search_chunks(
    notebook_id: str,
    query_text: str,
    query_embedding: list[float],
    match_count: int,
) -> list[dict[str, Any]]:
    return get_repository().hybrid_search_chunks(notebook_id, query_text, query_embedding, match_count)
```

- [ ] **Step 6: Run to confirm PASS**

```bash
python -m pytest tests/test_hybrid_retrieval.py -k "hybrid_search" -v
```
Expected: all PASS

- [ ] **Step 7: Confirm no database regressions**

```bash
python -m pytest tests/test_database.py tests/test_database_fixes.py -v
```
Expected: all PASS

---

### Task 8: `_coerce_and_score_chunks` helper

**Files:**
- Modify: `backend/app/services/rag.py`
- Modify: `backend/tests/test_hybrid_retrieval.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_hybrid_retrieval.py`:

```python
# ---------------------------------------------------------------------------
# Task 8 — _coerce_and_score_chunks helper
# ---------------------------------------------------------------------------


def _make_sources_by_id(*source_ids):
    return {
        sid: {"id": sid, "notebook_id": "nb-1", "title": f"Source {sid}", "summary": sid}
        for sid in source_ids
    }


def test_coerce_scores_rrf_chunks_by_rrf_score():
    """Chunks with rrf_score field are ranked by that score, not cosine."""
    from app.services.rag import _coerce_and_score_chunks

    settings = type("S", (), {"rag_max_chunks": 10, "rag_max_chunks_per_source": 2})()
    sources_by_id = _make_sources_by_id("src-a", "src-b")

    chunks = [
        {"source_id": "src-a", "content": "low score chunk",  "chunk_index": 0, "rrf_score": 0.1},
        {"source_id": "src-b", "content": "high score chunk", "chunk_index": 0, "rrf_score": 0.9},
    ]

    result = _coerce_and_score_chunks(chunks, [1.0, 0.0], settings, sources_by_id)

    assert len(result) == 2
    assert result[0]["id"] == "src-b"
    assert result[0]["_score"] == 0.9


def test_coerce_scores_float_embeddings_by_cosine():
    """Chunks with float list embeddings are ranked by cosine similarity."""
    from app.services.rag import _coerce_and_score_chunks

    settings = type("S", (), {"rag_max_chunks": 10, "rag_max_chunks_per_source": 2})()
    sources_by_id = _make_sources_by_id("src-1", "src-2")

    chunks = [
        {"source_id": "src-1", "content": "far",  "chunk_index": 0, "embedding": [0.0, 1.0]},
        {"source_id": "src-2", "content": "near", "chunk_index": 0, "embedding": [1.0, 0.0]},
    ]

    result = _coerce_and_score_chunks(chunks, [1.0, 0.0], settings, sources_by_id)

    assert result[0]["id"] == "src-2"
    assert result[0]["_score"] > result[1]["_score"]


def test_coerce_handles_string_embeddings(monkeypatch):
    """Spec test 3: pgvector-style string embeddings must be coerced, not score as zero."""
    from app.services.rag import _coerce_and_score_chunks

    settings = type("S", (), {"rag_max_chunks": 10, "rag_max_chunks_per_source": 2})()
    sources_by_id = _make_sources_by_id("src-1")

    chunks = [
        {
            "source_id": "src-1",
            "content": "first",
            "chunk_index": 0,
            "embedding": "[1.0, 0.0]",  # Supabase pgvector string
        },
        {
            "source_id": "src-1",
            "content": "second",
            "chunk_index": 1,
            "embedding": json.dumps([0.5, 0.5]),  # JSON string
        },
    ]

    result = _coerce_and_score_chunks(chunks, [1.0, 0.0], settings, sources_by_id)

    assert len(result) == 1  # both from src-1, capped to rag_max_chunks_per_source=2
    assert result[0]["_score"] > 0.0  # not zero — coercion worked


def test_coerce_enforces_per_source_cap():
    """rag_max_chunks_per_source limits chunks selected per source."""
    from app.services.rag import _coerce_and_score_chunks

    settings = type("S", (), {"rag_max_chunks": 10, "rag_max_chunks_per_source": 1})()
    sources_by_id = _make_sources_by_id("src-x")

    chunks = [
        {"source_id": "src-x", "content": "chunk A", "chunk_index": 0, "rrf_score": 0.9},
        {"source_id": "src-x", "content": "chunk B", "chunk_index": 1, "rrf_score": 0.8},
    ]

    result = _coerce_and_score_chunks(chunks, [1.0, 0.0], settings, sources_by_id)

    assert len(result[0]["_selected_chunks"]) == 1


def test_coerce_enforces_global_rag_max_chunks():
    """Spec test 5: rag_max_chunks total cap must be honoured across sources."""
    from app.services.rag import _coerce_and_score_chunks

    settings = type("S", (), {"rag_max_chunks": 3, "rag_max_chunks_per_source": 2})()
    sources_by_id = _make_sources_by_id("src-a", "src-b", "src-c")

    # 3 sources × 2 chunks = 6 chunks; global cap is 3
    chunks = [
        {"source_id": "src-a", "content": "a0", "chunk_index": 0, "rrf_score": 0.9},
        {"source_id": "src-a", "content": "a1", "chunk_index": 1, "rrf_score": 0.85},
        {"source_id": "src-b", "content": "b0", "chunk_index": 0, "rrf_score": 0.8},
        {"source_id": "src-b", "content": "b1", "chunk_index": 1, "rrf_score": 0.75},
        {"source_id": "src-c", "content": "c0", "chunk_index": 0, "rrf_score": 0.7},
        {"source_id": "src-c", "content": "c1", "chunk_index": 1, "rrf_score": 0.65},
    ]

    result = _coerce_and_score_chunks(chunks, [1.0, 0.0], settings, sources_by_id)

    total_chunks = sum(len(s["_selected_chunks"]) for s in result)
    assert total_chunks <= 3, f"Expected <=3 total chunks, got {total_chunks}"


def test_coerce_skips_unknown_sources():
    """Chunks whose source_id is not in sources_by_id are silently skipped."""
    from app.services.rag import _coerce_and_score_chunks

    settings = type("S", (), {"rag_max_chunks": 10, "rag_max_chunks_per_source": 2})()
    sources_by_id = _make_sources_by_id("known-src")

    chunks = [
        {"source_id": "unknown-src", "content": "stale chunk", "chunk_index": 0, "rrf_score": 0.9},
        {"source_id": "known-src",   "content": "good chunk",  "chunk_index": 0, "rrf_score": 0.8},
    ]

    result = _coerce_and_score_chunks(chunks, [1.0, 0.0], settings, sources_by_id)

    assert len(result) == 1
    assert result[0]["id"] == "known-src"
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
python -m pytest tests/test_hybrid_retrieval.py -k "coerce" -v
```
Expected: `ImportError: cannot import name '_coerce_and_score_chunks' from 'app.services.rag'`

- [ ] **Step 3: Add the helper to `rag.py`**

In `backend/app/services/rag.py`, add `import json` to the top imports, then add this function before `_fallback_answer`:

```python
def _coerce_and_score_chunks(
    chunks: list[dict],
    query_embedding: list[float],
    settings,
    sources_by_id: dict[str, dict],
) -> list[dict]:
    """Score *chunks*, group by source, and apply both chunk caps.

    Accepts chunks from either:
    - hybrid RPC results (have 'rrf_score' key) — score used directly
    - get_notebook_chunks fallback (have 'embedding') — cosine computed,
      embeddings coerced from pgvector strings if needed

    Returns sources list (each with '_selected_chunks' and '_score'), sorted
    descending by max chunk score.
    """
    scored_chunks = []
    for chunk in chunks:
        if "rrf_score" in chunk:
            score = float(chunk["rrf_score"])
        else:
            raw = chunk.get("embedding") or []
            if isinstance(raw, str):
                raw = json.loads(raw)
            emb = [float(v) for v in raw]
            score = cosine_similarity(query_embedding, emb)
        scored_chunks.append({**chunk, "_score": score})

    scored_chunks.sort(key=lambda c: c["_score"], reverse=True)

    selected_chunks_by_source: dict[str, list[dict]] = defaultdict(list)
    selected_total = 0

    for chunk in scored_chunks:
        if selected_total >= settings.rag_max_chunks:
            break
        sid = chunk["source_id"]
        if sid not in sources_by_id:
            continue
        if len(selected_chunks_by_source[sid]) >= settings.rag_max_chunks_per_source:
            continue
        selected_chunks_by_source[sid].append(chunk)
        selected_total += 1

    ranked_sources = []
    for source_id, selected in selected_chunks_by_source.items():
        source = dict(sources_by_id[source_id])
        source["_selected_chunks"] = [c["content"] for c in selected]
        source["_score"] = max(c["_score"] for c in selected)
        ranked_sources.append(source)

    ranked_sources.sort(key=lambda s: s["_score"], reverse=True)
    return ranked_sources
```

Also add `import json` near the top of `rag.py`:

```python
import json
import logging
from collections import defaultdict
from typing import Dict, List
```

- [ ] **Step 4: Run to confirm PASS**

```bash
python -m pytest tests/test_hybrid_retrieval.py -k "coerce" -v
```
Expected: all PASS

---

### Task 9: Refactor `retrieve_relevant_sources`

**Files:**
- Modify: `backend/app/services/rag.py`
- Modify: `backend/tests/test_hybrid_retrieval.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_hybrid_retrieval.py`:

```python
# ---------------------------------------------------------------------------
# Task 9 — retrieve_relevant_sources with hybrid path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_uses_hybrid_when_available(monkeypatch):
    """retrieve_relevant_sources calls hybrid_search_chunks in the happy path."""
    from app.services import rag

    fake_settings = type("S", (), {"rag_max_chunks": 4, "rag_max_chunks_per_source": 2})()
    monkeypatch.setattr(rag, "get_settings", lambda: fake_settings)

    async def fake_embed(text):
        return [1.0, 0.0]

    hybrid_called = []

    async def fake_hybrid(notebook_id, query_text, query_embedding, match_count):
        hybrid_called.append(match_count)
        return [
            {"source_id": "src-1", "content": "relevant chunk", "chunk_index": 0, "rrf_score": 0.9},
        ]

    monkeypatch.setattr(rag, "embed_document", fake_embed)
    monkeypatch.setattr(rag, "hybrid_search_chunks", fake_hybrid)

    sources = [{"id": "src-1", "notebook_id": "nb-1", "title": "Source 1", "summary": "s"}]
    result = await rag.retrieve_relevant_sources("query text", sources, top_k=5)

    assert len(hybrid_called) == 1
    assert hybrid_called[0] == 4 * 3  # rag_max_chunks * 3 = 12
    assert len(result) > 0
    assert result[0]["id"] == "src-1"
    assert result[0]["_selected_chunks"] == ["relevant chunk"]


@pytest.mark.asyncio
async def test_retrieve_fallback_on_hybrid_exception(monkeypatch):
    """Spec test 3: when hybrid raises, fallback to get_notebook_chunks with coercion."""
    from app.services import rag

    fake_settings = type("S", (), {"rag_max_chunks": 4, "rag_max_chunks_per_source": 2})()
    monkeypatch.setattr(rag, "get_settings", lambda: fake_settings)

    async def fake_embed(text):
        return [1.0, 0.0]

    async def failing_hybrid(*args, **kwargs):
        raise RuntimeError("RPC unavailable")

    # Fallback chunks with pgvector string embeddings
    async def fake_get_chunks(notebook_id):
        return [
            {
                "source_id": "src-1",
                "content": "fallback content",
                "chunk_index": 0,
                "embedding": "[1.0, 0.0]",  # pgvector string — must be coerced
            }
        ]

    monkeypatch.setattr(rag, "embed_document", fake_embed)
    monkeypatch.setattr(rag, "hybrid_search_chunks", failing_hybrid)
    monkeypatch.setattr(rag, "get_notebook_chunks", fake_get_chunks)

    sources = [{"id": "src-1", "notebook_id": "nb-1", "title": "Source 1", "summary": "s"}]
    result = await rag.retrieve_relevant_sources("query", sources, top_k=5)

    assert len(result) > 0
    assert result[0]["_score"] > 0.0  # coercion worked — not zero


@pytest.mark.asyncio
async def test_retrieve_hybrid_empty_falls_back(monkeypatch):
    """If hybrid returns empty list, fall back to get_notebook_chunks."""
    from app.services import rag

    fake_settings = type("S", (), {"rag_max_chunks": 4, "rag_max_chunks_per_source": 2})()
    monkeypatch.setattr(rag, "get_settings", lambda: fake_settings)

    async def fake_embed(text):
        return [1.0, 0.0]

    async def empty_hybrid(*args):
        return []

    fallback_called = []

    async def fake_get_chunks(notebook_id):
        fallback_called.append(notebook_id)
        return [
            {"source_id": "src-1", "content": "chunk", "chunk_index": 0, "embedding": [1.0, 0.0]}
        ]

    monkeypatch.setattr(rag, "embed_document", fake_embed)
    monkeypatch.setattr(rag, "hybrid_search_chunks", empty_hybrid)
    monkeypatch.setattr(rag, "get_notebook_chunks", fake_get_chunks)

    sources = [{"id": "src-1", "notebook_id": "nb-1", "title": "Source 1", "summary": "s"}]
    result = await rag.retrieve_relevant_sources("query", sources, top_k=5)

    assert fallback_called == ["nb-1"]
    assert len(result) > 0


@pytest.mark.asyncio
async def test_retrieve_preserves_rag_max_chunks_cap(monkeypatch):
    """Spec test 5: global rag_max_chunks cap is preserved end-to-end."""
    from app.services import rag

    fake_settings = type("S", (), {"rag_max_chunks": 2, "rag_max_chunks_per_source": 2})()
    monkeypatch.setattr(rag, "get_settings", lambda: fake_settings)

    async def fake_embed(text):
        return [1.0, 0.0]

    async def fake_hybrid(notebook_id, query_text, query_embedding, match_count):
        # Return 6 chunks across 3 sources — global cap must trim to 2
        return [
            {"source_id": "src-a", "content": "a0", "chunk_index": 0, "rrf_score": 0.9},
            {"source_id": "src-a", "content": "a1", "chunk_index": 1, "rrf_score": 0.85},
            {"source_id": "src-b", "content": "b0", "chunk_index": 0, "rrf_score": 0.8},
            {"source_id": "src-b", "content": "b1", "chunk_index": 1, "rrf_score": 0.75},
            {"source_id": "src-c", "content": "c0", "chunk_index": 0, "rrf_score": 0.7},
            {"source_id": "src-c", "content": "c1", "chunk_index": 1, "rrf_score": 0.65},
        ]

    monkeypatch.setattr(rag, "embed_document", fake_embed)
    monkeypatch.setattr(rag, "hybrid_search_chunks", fake_hybrid)

    sources = [
        {"id": sid, "notebook_id": "nb-1", "title": f"S {sid}", "summary": sid}
        for sid in ("src-a", "src-b", "src-c")
    ]
    result = await rag.retrieve_relevant_sources("query", sources, top_k=10)

    total_chunks = sum(len(s["_selected_chunks"]) for s in result)
    assert total_chunks <= 2, f"Global cap violated: got {total_chunks} chunks"


@pytest.mark.asyncio
async def test_retrieve_stopword_query_returns_results(monkeypatch):
    """Spec test 4: a stopword-only query still returns results (vector path handles it)."""
    from app.services import rag

    fake_settings = type("S", (), {"rag_max_chunks": 4, "rag_max_chunks_per_source": 2})()
    monkeypatch.setattr(rag, "get_settings", lambda: fake_settings)

    async def fake_embed(text):
        return [1.0, 0.0]

    # Simulate what the RPC returns for a stopword-only query:
    # FTS produces nothing, vector path still returns results with rrf_score from vec side
    async def fake_hybrid(notebook_id, query_text, query_embedding, match_count):
        return [
            {"source_id": "src-1", "content": "vector result", "chunk_index": 0, "rrf_score": 0.016}
        ]

    monkeypatch.setattr(rag, "embed_document", fake_embed)
    monkeypatch.setattr(rag, "hybrid_search_chunks", fake_hybrid)

    sources = [{"id": "src-1", "notebook_id": "nb-1", "title": "Source 1", "summary": "s"}]
    # "the a is" — all English stopwords
    result = await rag.retrieve_relevant_sources("the a is", sources, top_k=5)

    assert len(result) > 0, "Stopword query must still return vector-ranked results"
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
python -m pytest tests/test_hybrid_retrieval.py -k "retrieve" -v
```
Expected: FAIL — `rag.hybrid_search_chunks` not yet imported in rag.py

- [ ] **Step 3: Rewrite `retrieve_relevant_sources` in `rag.py`**

The full updated `rag.py` (replace the existing `retrieve_relevant_sources` function, keep everything else):

```python
async def retrieve_relevant_sources(query: str, sources: List[Dict], top_k: int = 5) -> List[Dict]:
    if not sources:
        logger.info("retrieve_relevant_sources called with no sources")
        return []

    logger.info(
        "Retrieving relevant sources for query: %r (top_k=%d, sources=%d)",
        query[:80], top_k, len(sources),
    )

    notebook_id = sources[0].get("notebook_id")
    query_embedding = await embed_document(query)

    # ── No notebook_id: source-level cosine only ────────────────────────────
    if not notebook_id:
        scored_sources = []
        for source in sources:
            raw = source.get("embedding") or []
            if isinstance(raw, str):
                raw = json.loads(raw)
            emb = [float(v) for v in raw]
            if not emb:
                continue
            scored_sources.append({**source, "_score": cosine_similarity(query_embedding, emb)})
        scored_sources.sort(key=lambda item: item["_score"], reverse=True)
        result = scored_sources[:top_k]
        logger.info("Source-level retrieval (no chunks): top scores=%s", [round(s["_score"], 4) for s in result])
        return result

    settings = get_settings()
    sources_by_id = {source["id"]: dict(source) for source in sources}

    # ── Hybrid search path ──────────────────────────────────────────────────
    try:
        hybrid_chunks = await hybrid_search_chunks(
            notebook_id,
            query,
            query_embedding,
            match_count=settings.rag_max_chunks * 3,
        )
        if hybrid_chunks:
            ranked = _coerce_and_score_chunks(hybrid_chunks, query_embedding, settings, sources_by_id)
            result = ranked[:top_k]
            logger.info(
                "Hybrid retrieval complete — selected %d sources, top scores: %s",
                len(result),
                [round(s["_score"], 4) for s in result],
            )
            return result
        logger.info("Hybrid search returned empty — falling back to cosine")
    except Exception as exc:
        logger.warning("Hybrid search failed (%s) — falling back to cosine", exc)

    # ── Cosine fallback ─────────────────────────────────────────────────────
    chunks = await get_notebook_chunks(notebook_id)
    if not chunks:
        logger.warning("No chunks found for notebook %s — falling back to source-level retrieval", notebook_id)
        scored_sources = []
        for source in sources:
            raw = source.get("embedding") or []
            if isinstance(raw, str):
                raw = json.loads(raw)
            emb = [float(v) for v in raw]
            if not emb:
                continue
            scored_sources.append({**source, "_score": cosine_similarity(query_embedding, emb)})
        scored_sources.sort(key=lambda item: item["_score"], reverse=True)
        return scored_sources[:top_k]

    ranked = _coerce_and_score_chunks(chunks, query_embedding, settings, sources_by_id)
    result = ranked[:top_k]
    logger.info(
        "Cosine fallback complete — selected %d sources, top scores: %s",
        len(result),
        [round(s["_score"], 4) for s in result],
    )
    return result
```

Also add this import near the top of `rag.py` (after the existing imports):

```python
from app.database import get_notebook_chunks, hybrid_search_chunks
```

- [ ] **Step 4: Run to confirm PASS**

```bash
python -m pytest tests/test_hybrid_retrieval.py -v
```
Expected: all PASS

- [ ] **Step 5: Confirm no regressions in existing RAG + router tests**

```bash
python -m pytest tests/test_config_rag_fixes.py tests/test_routers.py tests/test_smart_crawler.py -v
```
Expected: all PASS

- [ ] **Step 6: Run the full test suite**

```bash
python -m pytest tests/ -v --tb=short
```
Expected: all PASS (excluding any integration tests requiring a live Supabase/Redis connection)

---

## Final checklist

- [ ] `FIRECRAWL_API_KEY` added to `backend/.env` (starts with `fc-`)
- [ ] Supabase migration applied (`add_source_chunks_fts.sql`)
- [ ] Supabase RPC applied (`rpc_hybrid_search_chunks.sql`) — verify function appears in Supabase → Database → Functions
- [ ] `firecrawl-py` installed: `pip install -r requirements.txt` in the backend virtualenv
- [ ] Full test suite passes: `python -m pytest tests/ -v --tb=short`
