from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Fix 1 — new config fields
# ---------------------------------------------------------------------------


def test_new_config_fields_have_defaults():
    config = importlib.import_module("app.config")
    importlib.reload(config)
    settings = config.Settings()

    assert settings.edge_similarity_threshold == 0.4
    assert settings.rag_max_chunks == 8
    assert settings.rag_max_chunks_per_source == 2
    assert settings.edge_label_batch_size == 20


def test_config_fields_overridable_via_env(monkeypatch):
    monkeypatch.setenv("EDGE_SIMILARITY_THRESHOLD", "0.7")
    monkeypatch.setenv("RAG_MAX_CHUNKS", "12")
    monkeypatch.setenv("RAG_MAX_CHUNKS_PER_SOURCE", "4")
    monkeypatch.setenv("EDGE_LABEL_BATCH_SIZE", "50")

    config = importlib.import_module("app.config")
    importlib.reload(config)
    settings = config.Settings()

    assert settings.edge_similarity_threshold == 0.7
    assert settings.rag_max_chunks == 12
    assert settings.rag_max_chunks_per_source == 4
    assert settings.edge_label_batch_size == 50


# ---------------------------------------------------------------------------
# Fix 2 — RAG respects config values
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rag_respects_max_chunks_config(monkeypatch):
    from app.services import rag

    # Build a fake settings object with tight limits
    fake_settings = MagicMock()
    fake_settings.rag_max_chunks = 3
    fake_settings.rag_max_chunks_per_source = 1

    monkeypatch.setattr(rag, "get_settings", lambda: fake_settings)

    # Embed: query gets [1, 0], everything else gets [1, 0] (all equally relevant)
    async def fake_embed_document(text: str):
        return [1.0, 0.0]

    monkeypatch.setattr(rag, "embed_document", fake_embed_document)

    # 4 sources, each with 2 chunks — without limits we would get 8 total chunks
    source_ids = ["src-a", "src-b", "src-c", "src-d"]
    chunks = []
    for sid in source_ids:
        for idx in range(2):
            chunks.append(
                {
                    "source_id": sid,
                    "chunk_index": idx,
                    "content": f"content {sid} chunk {idx}",
                    "embedding": [1.0, 0.0],
                }
            )

    async def fake_get_notebook_chunks(notebook_id: str):
        return chunks

    monkeypatch.setattr(rag, "get_notebook_chunks", fake_get_notebook_chunks)

    sources = [
        {"id": sid, "notebook_id": "nb-test", "title": f"Source {sid}", "summary": sid}
        for sid in source_ids
    ]

    result = await rag.retrieve_relevant_sources("query", sources, top_k=10)

    # Collect selected chunks across all returned sources
    total_chunks = sum(len(src.get("_selected_chunks") or []) for src in result)
    max_per_source = max(
        (len(src.get("_selected_chunks") or []) for src in result),
        default=0,
    )

    assert total_chunks <= 3, f"Expected <=3 total chunks, got {total_chunks}"
    assert max_per_source <= 1, f"Expected <=1 chunk per source, got {max_per_source}"


# ---------------------------------------------------------------------------
# Fix 3 — /health endpoint with Celery check
# ---------------------------------------------------------------------------


def test_health_endpoint_ok(monkeypatch):
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    import app.main as main_module

    fake_control = MagicMock()
    fake_control.ping.return_value = {"worker@host": {"ok": "pong"}}

    with patch.object(main_module.celery_app, "control", fake_control, create=True):
        client = TestClient(main_module.app)
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["celery"] == "ok"


def test_health_endpoint_celery_down(monkeypatch):
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    import app.main as main_module

    fake_control = MagicMock()
    fake_control.ping.side_effect = Exception("broker unreachable")

    with patch.object(main_module.celery_app, "control", fake_control, create=True):
        client = TestClient(main_module.app)
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["celery"] == "unavailable"
