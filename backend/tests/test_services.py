from __future__ import annotations

import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import crawler, discovery, graph, processor, rag
from app.services.chunking import chunk_text


@pytest.mark.asyncio
async def test_discovery_fallback_returns_related_urls(monkeypatch):
    monkeypatch.setattr(discovery, "genai", None, raising=False)
    monkeypatch.setattr(discovery, "get_settings", lambda: type("S", (), {"has_gemini": False, "max_discovery_results": 3})())

    results = await discovery.discover_related_sources(
        "Neural networks are transforming healthcare diagnostics. https://example.com/seed",
        max_results=3,
    )

    # Fallback now correctly returns [] instead of junk search-engine URLs
    assert results == []


@pytest.mark.asyncio
async def test_extract_seed_title_falls_back_to_short_words(monkeypatch):
    monkeypatch.setattr(discovery, "genai", None, raising=False)
    monkeypatch.setattr(discovery, "get_settings", lambda: type("S", (), {"has_gemini": False})())

    title = await discovery.extract_seed_title("A short notebook about neural search for medicine")
    assert title
    assert len(title.split()) <= 5


@pytest.mark.asyncio
async def test_crawler_falls_back_to_html_text(monkeypatch):
    _LONG_BODY = (
        "<html><head><title>Example</title></head><body>"
        "Hello world from page content. This body is long enough to pass the fifty character minimum threshold."
        "</body></html>"
    )

    class FakeResponse:
        text = _LONG_BODY
        headers = {"content-type": "text/html"}

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def head(self, url, **kwargs):
            return FakeResponse()

        async def get(self, url, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(crawler, "trafilatura", None, raising=False)
    monkeypatch.setattr(crawler.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(crawler, "get_settings", lambda: type("S", (), {"max_document_chars": 200})())

    result = await crawler.crawl_url("https://example.com")
    assert result is not None
    assert "text" in result
    assert "Hello world from page content" in result["text"]
    assert "<html>" not in result["text"]
    assert "<body>" not in result["text"]


@pytest.mark.asyncio
async def test_processor_fallback_summary_and_embedding(monkeypatch):
    monkeypatch.setattr(processor, "genai", None, raising=False)
    expected_dim = processor.get_settings().embedding_dimension

    summary = await processor.summarize_document(
        "Neural networks learn patterns. They are useful for text and vision.",
        "Neural Networks",
    )
    embedding = await processor.embed_document("Neural networks learn patterns.")

    assert isinstance(summary, str)
    assert "Neural networks learn patterns." in summary
    assert len(embedding) == expected_dim
    assert any(value != 0.0 for value in embedding)


@pytest.mark.asyncio
async def test_embed_chunks_adds_embeddings_to_chunk_output(monkeypatch):
    expected_dim = processor.get_settings().embedding_dimension

    async def fake_embed_document(text: str):
        return [float(len(text))] + [0.0] * (expected_dim - 1)

    monkeypatch.setattr(processor, "embed_document", fake_embed_document)

    chunks = await processor.embed_chunks(
        "Sentence one is long enough to force splitting into multiple chunks. "
        "Sentence two continues the discussion. "
        "Sentence three adds more detail so overlap remains meaningful."
    )

    assert chunks
    assert all("embedding" in chunk for chunk in chunks)
    assert all(len(chunk["embedding"]) == expected_dim for chunk in chunks)


@pytest.mark.asyncio
async def test_embed_chunks_skips_wrong_dimension_embeddings(monkeypatch, caplog):
    expected_dim = processor.get_settings().embedding_dimension
    wrong_dim = expected_dim - 1 if expected_dim > 1 else expected_dim + 1

    fake_chunks = [
        {"chunk_index": 0, "content": "chunk zero content", "char_start": 0, "char_end": 18},
        {"chunk_index": 1, "content": "chunk one content", "char_start": 18, "char_end": 35},
        {"chunk_index": 2, "content": "chunk two content", "char_start": 35, "char_end": 52},
    ]
    monkeypatch.setattr(processor, "chunk_text", lambda text, **kwargs: fake_chunks)

    async def fake_embed_document(text: str):
        if "zero" in text:
            return [0.5] * wrong_dim
        return [0.1] * expected_dim

    monkeypatch.setattr(processor, "embed_document", fake_embed_document)

    with caplog.at_level("WARNING", logger="app.services.processor"):
        chunks = await processor.embed_chunks("some text")

    assert [chunk["content"] for chunk in chunks] == ["chunk one content", "chunk two content"]
    assert all(len(chunk["embedding"]) == expected_dim for chunk in chunks)
    assert any("unexpected dimension" in record.message for record in caplog.records)


def test_chunk_text_uses_overlap_and_boundaries():
    text = (
        "Paragraph one explains the first idea in enough detail to exceed the chunk size target. "
        "It keeps going so the chunker needs to split on a sensible boundary.\n\n"
        "Paragraph two continues the discussion with more detail and examples."
    )

    chunks = chunk_text(text, target_size=100, overlap=20)
    assert len(chunks) >= 2
    assert chunks[0]["char_end"] > chunks[1]["char_start"]
    assert chunks[0]["content"]
    assert chunks[1]["content"]


def test_graph_similarity_and_edge_generation_from_chunk_centroids():
    docs = [
        {"id": "a", "title": "Neural Search"},
        {"id": "b", "title": "Neural Search Methods"},
        {"id": "c", "title": "Market Analysis"},
    ]
    chunks = [
        {"source_id": "a", "embedding": [1.0, 0.0, 0.0]},
        {"source_id": "a", "embedding": [0.8, 0.2, 0.0]},
        {"source_id": "b", "embedding": [0.9, 0.1, 0.0]},
        {"source_id": "c", "embedding": [0.0, 0.0, 1.0]},
    ]

    edges = graph.compute_edges(docs, chunks, threshold=0.5)
    assert [set((edge["source_a"], edge["source_b"])) for edge in edges] == [{"a", "b"}]
    assert edges[0]["similarity"] > 0.5


@pytest.mark.asyncio
async def test_graph_fallback_labels(monkeypatch):
    monkeypatch.setattr(graph, "genai", None, raising=False)
    edges = [{"source_a": "a", "source_b": "b", "similarity": 0.91}]
    docs_by_id = {
        "a": {"title": "Neural Search", "summary": "A"},
        "b": {"title": "Neural Search Methods", "summary": "B"},
    }

    labeled = await graph.generate_edge_labels(edges, docs_by_id)
    assert labeled[0]["relationship"]


@pytest.mark.asyncio
async def test_rag_ranking_and_fallback_answer(monkeypatch):
    async def fake_embed_document(text: str):
        return [1.0, 0.0] if text == "query" else [0.0, 1.0]

    monkeypatch.setattr(rag, "embed_document", fake_embed_document)
    monkeypatch.setattr(rag, "genai", None, raising=False)
    async def fake_get_notebook_chunks(notebook_id: str):
        return [
            {
                "source_id": "close",
                "chunk_index": 0,
                "content": "close chunk",
                "embedding": [0.9, 0.1],
            },
            {
                "source_id": "far",
                "chunk_index": 0,
                "content": "far chunk",
                "embedding": [0.0, 1.0],
            },
        ]

    monkeypatch.setattr(rag, "get_notebook_chunks", fake_get_notebook_chunks)

    sources = [
        {"id": "close", "notebook_id": "nb-1", "title": "Close Match", "summary": "close"},
        {"id": "far", "notebook_id": "nb-1", "title": "Far Match", "summary": "far"},
    ]

    relevant = await rag.retrieve_relevant_sources("query", sources, top_k=1)
    assert relevant[0]["id"] == "close"
    assert relevant[0]["_selected_chunks"] == ["close chunk"]

    answer = await rag.generate_answer("query", relevant, chat_history=[])
    assert "Close Match" in answer["content"]
    assert answer["sources_cited"] == ["close"]


@pytest.mark.asyncio
async def test_rag_limits_chunks_per_source_and_total(monkeypatch):
    async def fake_embed_document(text: str):
        return [1.0, 0.0]

    async def fake_get_notebook_chunks(notebook_id: str):
        chunks = []
        for index in range(5):
            chunks.append(
                {
                    "source_id": "a",
                    "chunk_index": index,
                    "content": f"a-{index}",
                    "embedding": [0.95 - (index * 0.01), 0.0],
                }
            )
        for index in range(5):
            chunks.append(
                {
                    "source_id": "b",
                    "chunk_index": index,
                    "content": f"b-{index}",
                    "embedding": [0.9 - (index * 0.01), 0.0],
                }
            )
        for index in range(5):
            chunks.append(
                {
                    "source_id": "c",
                    "chunk_index": index,
                    "content": f"c-{index}",
                    "embedding": [0.85 - (index * 0.01), 0.0],
                }
            )
        for index in range(5):
            chunks.append(
                {
                    "source_id": "d",
                    "chunk_index": index,
                    "content": f"d-{index}",
                    "embedding": [0.8 - (index * 0.01), 0.0],
                }
            )
        for index in range(5):
            chunks.append(
                {
                    "source_id": "e",
                    "chunk_index": index,
                    "content": f"e-{index}",
                    "embedding": [0.75 - (index * 0.01), 0.0],
                }
            )
        return chunks

    monkeypatch.setattr(rag, "embed_document", fake_embed_document)
    monkeypatch.setattr(rag, "get_notebook_chunks", fake_get_notebook_chunks)

    sources = [
        {"id": "a", "notebook_id": "nb-1", "title": "A"},
        {"id": "b", "notebook_id": "nb-1", "title": "B"},
        {"id": "c", "notebook_id": "nb-1", "title": "C"},
        {"id": "d", "notebook_id": "nb-1", "title": "D"},
        {"id": "e", "notebook_id": "nb-1", "title": "E"},
    ]

    relevant = await rag.retrieve_relevant_sources("query", sources, top_k=5)

    assert [source["id"] for source in relevant] == ["a", "b", "c", "d"]
    assert all(len(source["_selected_chunks"]) <= 2 for source in relevant)
    assert sum(len(source["_selected_chunks"]) for source in relevant) == 8
