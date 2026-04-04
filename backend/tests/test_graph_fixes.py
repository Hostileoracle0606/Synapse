from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import graph, processor

EXPECTED_DIM = processor.get_settings().embedding_dimension


# ---------------------------------------------------------------------------
# Fix 1 tests: centroid_from_chunk_embeddings dimension validation
# ---------------------------------------------------------------------------


def _make_embedding(dim: int, value: float = 1.0) -> list[float]:
    """Return a simple embedding of the given dimension."""
    vec = [value / dim] * dim
    return vec


def test_centroid_all_valid():
    """All configured-dim embeddings produce a valid centroid with no errors."""
    embeddings = [_make_embedding(EXPECTED_DIM, float(i + 1)) for i in range(10)]
    centroid = graph.centroid_from_chunk_embeddings(embeddings)
    assert len(centroid) == EXPECTED_DIM
    assert any(v != 0.0 for v in centroid)


def test_centroid_mismatched_dims(caplog):
    """1 wrong-dim embedding out of 10 (10%) → warning logged, centroid still produced from 9."""
    good = [_make_embedding(EXPECTED_DIM, float(i + 1)) for i in range(9)]
    bad = [_make_embedding(EXPECTED_DIM - 1 if EXPECTED_DIM > 1 else EXPECTED_DIM + 1)]
    embeddings = good + bad

    with caplog.at_level(logging.WARNING, logger="app.services.graph"):
        centroid = graph.centroid_from_chunk_embeddings(embeddings)

    assert len(centroid) == EXPECTED_DIM
    # Warning should mention the skipped chunk
    assert any("1" in record.message and "10" in record.message for record in caplog.records), (
        f"Expected a warning about 1/10 skipped embeddings, got: {[r.message for r in caplog.records]}"
    )


def test_centroid_majority_corrupt():
    """6 out of 10 wrong-dim embeddings (60%) → ValueError raised."""
    good = [_make_embedding(EXPECTED_DIM, float(i + 1)) for i in range(4)]
    bad = [_make_embedding(EXPECTED_DIM - 1 if EXPECTED_DIM > 1 else EXPECTED_DIM + 1)] * 6
    embeddings = good + bad

    with pytest.raises(ValueError, match="Data corruption"):
        graph.centroid_from_chunk_embeddings(embeddings)


# ---------------------------------------------------------------------------
# Fix 2 tests: embedding dimension validated at write time in processor.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embedding_dim_validated_at_write(monkeypatch, caplog):
    """A wrong-dimension embedding from the API is skipped and the valid chunks are stored."""
    # Provide 3 pre-made chunks so the test is independent of chunking behaviour.
    fake_chunks = [
        {"chunk_index": 0, "content": "chunk zero content", "char_start": 0, "char_end": 18},
        {"chunk_index": 1, "content": "chunk one content", "char_start": 18, "char_end": 35},
        {"chunk_index": 2, "content": "chunk two content", "char_start": 35, "char_end": 52},
    ]
    monkeypatch.setattr(processor, "chunk_text", lambda text, **kwargs: fake_chunks)
    wrong_dim = EXPECTED_DIM - 1 if EXPECTED_DIM > 1 else EXPECTED_DIM + 1

    async def fake_embed_document(text: str):
        if "zero" in text:
            return [0.5] * wrong_dim
        return [0.1] * EXPECTED_DIM

    monkeypatch.setattr(processor, "embed_document", fake_embed_document)

    with caplog.at_level(logging.WARNING, logger="app.services.processor"):
        chunks = await processor.embed_chunks("some text")

    assert len(chunks) == 2, f"Expected 2 valid chunks, got {len(chunks)}"
    assert [chunk["content"] for chunk in chunks] == ["chunk one content", "chunk two content"]
    assert all(len(chunk["embedding"]) == EXPECTED_DIM for chunk in chunks)

    # A warning should have been logged
    assert any(str(wrong_dim) in record.message or "unexpected dimension" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Fix 3 tests: edge label batching processes all edges
# ---------------------------------------------------------------------------


def _make_edges(n: int) -> list[dict]:
    return [
        {"source_a": f"src_{i}", "source_b": f"src_{i + 1}", "similarity": 0.9}
        for i in range(n)
    ]


def _make_docs_by_id(edges: list[dict]) -> dict:
    docs = {}
    for edge in edges:
        for key in ("source_a", "source_b"):
            doc_id = edge[key]
            if doc_id not in docs:
                docs[doc_id] = {"title": doc_id, "summary": f"Summary of {doc_id}"}
    return docs


@pytest.mark.asyncio
async def test_edge_label_batch_processes_all_edges(monkeypatch):
    """35 edges are all labeled (no edge defaults to 'related topics' due to batch cutoff)."""
    edges = _make_edges(35)
    docs_by_id = _make_docs_by_id(edges)

    batch_size = 20

    def fake_get_settings():
        s = MagicMock()
        s.gemini_api_key = "fake-key"
        s.gemini_model = "fake-model"
        s.edge_label_batch_size = batch_size
        return s

    call_number = [0]

    def make_fake_client():
        client = MagicMock()

        def generate_content(model, contents):
            batch_index = call_number[0]
            call_number[0] += 1
            # Determine how many edges are in this batch
            start = batch_index * batch_size
            end = min(start + batch_size, 35)
            count = end - start
            text = "\n".join(f"label for edge {start + i}" for i in range(count))
            resp = MagicMock()
            resp.text = text
            return resp

        client.models.generate_content = generate_content
        return client

    monkeypatch.setattr(graph, "get_settings", fake_get_settings)
    monkeypatch.setattr(graph, "get_gemini_client", make_fake_client)

    labeled = await graph.generate_edge_labels(edges, docs_by_id)

    assert len(labeled) == 35
    # Every edge should have a non-"related topics" relationship (all batches returned labels)
    for edge in labeled:
        assert edge.get("relationship") != "related topics", (
            f"Edge {edge['source_a']}->{edge['source_b']} got default 'related topics'"
        )


@pytest.mark.asyncio
async def test_edge_label_malformed_response(monkeypatch):
    """Gemini returns only 5 labels for a 10-edge batch → 5 edges labeled, 5 get 'related topics'."""
    edges = _make_edges(10)
    docs_by_id = _make_docs_by_id(edges)

    def fake_get_settings():
        s = MagicMock()
        s.gemini_api_key = "fake-key"
        s.gemini_model = "fake-model"
        s.edge_label_batch_size = 20  # batch large enough to fit all 10
        return s

    def make_fake_client():
        client = MagicMock()
        resp = MagicMock()
        # Only 5 labels for 10 edges
        resp.text = "\n".join(f"label {i}" for i in range(5))
        client.models.generate_content.return_value = resp
        return client

    monkeypatch.setattr(graph, "get_settings", fake_get_settings)
    monkeypatch.setattr(graph, "get_gemini_client", make_fake_client)

    labeled = await graph.generate_edge_labels(edges, docs_by_id)

    assert len(labeled) == 10  # no crash

    # First 5 edges should have labels from Gemini
    for edge in labeled[:5]:
        assert edge["relationship"] != "related topics", (
            f"Expected a real label for edge {edge['source_a']}"
        )

    # Last 5 edges should default to "related topics"
    for edge in labeled[5:]:
        assert edge["relationship"] == "related topics", (
            f"Expected 'related topics' for edge {edge['source_a']}, got {edge['relationship']!r}"
        )
