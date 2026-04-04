from __future__ import annotations

import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models import ChatMessage, ChatRequest, CreateNotebookRequest, NotebookResponse
from pydantic import ValidationError


def test_create_notebook_request_requires_seed():
    with pytest.raises(ValidationError):
        CreateNotebookRequest()


def test_create_notebook_request_accepts_url_or_text():
    req = CreateNotebookRequest(seed_url="https://example.com")
    assert req.seed_url == "https://example.com"

    req = CreateNotebookRequest(seed_text="seed text")
    assert req.seed_text == "seed text"


def test_chat_request_rejects_empty_message():
    with pytest.raises(ValidationError):
        ChatRequest(message="")


def test_response_models_use_fresh_lists():
    notebook = NotebookResponse(id="n1", title="Notebook", status="ready")
    message = ChatMessage(role="assistant", content="hello")

    notebook.sources.append(object())  # type: ignore[arg-type]
    message.sources_cited.append("s1")

    assert NotebookResponse(id="n2", title="Notebook 2", status="discovering").sources == []
    assert ChatMessage(role="user", content="hi").sources_cited == []
