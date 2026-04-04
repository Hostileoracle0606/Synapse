from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.main import app
from app.routers import chat, notebooks


client = TestClient(app)


def test_health_endpoint_reports_services():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_notebook_from_text(monkeypatch):
    created = {"called": False}
    enqueued: list[tuple[str, str]] = []

    async def fake_create_notebook(title, seed_url=None, seed_text=None):
        created["called"] = True
        return {"id": "nb-1", "title": title, "status": "discovering"}

    async def fake_extract_seed_title(seed_text):
        return "Generated Title"

    def fake_enqueue(notebook_id, seed_text):
        enqueued.append((notebook_id, seed_text))

    monkeypatch.setattr(notebooks, "create_notebook", fake_create_notebook)
    monkeypatch.setattr(notebooks, "extract_seed_title", fake_extract_seed_title)
    monkeypatch.setattr(notebooks, "enqueue_notebook_processing", fake_enqueue)

    response = client.post("/api/notebooks", json={"seed_text": "Some research notes"})

    assert response.status_code == 200
    assert response.json() == {"id": "nb-1", "title": "Generated Title", "status": "discovering"}
    assert created["called"] is True
    assert enqueued == [("nb-1", "Some research notes")]


def test_create_notebook_from_url_failure(monkeypatch):
    async def fake_smart_crawl(url, source_type="webpage"):
        return None

    monkeypatch.setattr(notebooks, "smart_crawl_url", fake_smart_crawl)

    response = client.post("/api/notebooks", json={"seed_url": "https://example.com"})

    assert response.status_code == 400


def test_get_notebook_not_found(monkeypatch):
    async def fake_get_notebook(notebook_id):
        return None

    monkeypatch.setattr(notebooks, "get_notebook", fake_get_notebook)

    response = client.get("/api/notebooks/missing")

    assert response.status_code == 404


def test_chat_history_and_send_message(monkeypatch):
    notebook = {"id": "nb-1", "title": "Notebook", "status": "ready"}
    messages: list[dict] = []

    async def fake_get_notebook(notebook_id):
        return notebook

    async def fake_get_messages(notebook_id):
        return messages

    async def fake_get_sources(notebook_id):
        return [{"id": "s1", "status": "ready", "title": "Source 1"}]

    async def fake_retrieve_relevant_sources(query, sources, top_k=5):
        return sources

    async def fake_generate_answer(query, relevant_sources, chat_history):
        return {"content": "Answer", "sources_cited": ["s1"]}

    async def fake_add_message(notebook_id, role, content, sources_cited=None):
        message = {
            "id": f"{role}-1",
            "notebook_id": notebook_id,
            "role": role,
            "content": content,
            "sources_cited": sources_cited or [],
            "created_at": None,
        }
        messages.append(message)
        return message

    monkeypatch.setattr(chat, "get_notebook", fake_get_notebook)
    monkeypatch.setattr(chat, "get_messages", fake_get_messages)
    monkeypatch.setattr(chat, "get_sources", fake_get_sources)
    monkeypatch.setattr(chat, "retrieve_relevant_sources", fake_retrieve_relevant_sources)
    monkeypatch.setattr(chat, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(chat, "add_message", fake_add_message)

    history_response = client.get("/api/notebooks/nb-1/chat")
    assert history_response.status_code == 200
    assert history_response.json() == []

    send_response = client.post("/api/notebooks/nb-1/chat", json={"message": "What matters?"})
    assert send_response.status_code == 200
    assert send_response.json()["role"] == "assistant"
    assert send_response.json()["sources_cited"] == ["s1"]
    assert [message["role"] for message in messages] == ["user", "assistant"]


def test_chat_rejects_unprocessed_notebook(monkeypatch):
    async def fake_get_notebook(notebook_id):
        return {"id": notebook_id, "title": "Notebook", "status": "discovering"}

    async def fake_get_sources(notebook_id):
        return [{"id": "s1", "status": "processing", "embedding": None}]

    async def fake_get_messages(notebook_id):
        return []

    recorded = []

    async def fake_add_message(notebook_id, role, content, sources_cited=None):
        recorded.append((notebook_id, role, content, sources_cited or []))
        return {
            "id": f"{role}-1",
            "notebook_id": notebook_id,
            "role": role,
            "content": content,
            "sources_cited": sources_cited or [],
            "created_at": None,
        }

    monkeypatch.setattr(chat, "get_notebook", fake_get_notebook)
    monkeypatch.setattr(chat, "get_sources", fake_get_sources)
    monkeypatch.setattr(chat, "get_messages", fake_get_messages)
    monkeypatch.setattr(chat, "add_message", fake_add_message)

    response = client.post("/api/notebooks/nb-1/chat", json={"message": "Hello"})
    assert response.status_code == 400
    assert recorded == [("nb-1", "user", "Hello", [])]
