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
