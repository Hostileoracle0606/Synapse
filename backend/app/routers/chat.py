from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException

from app.database import add_message, get_messages, get_notebook, get_sources
from app.models import ChatMessage, ChatRequest
from app.services.rag import generate_answer

router = APIRouter(prefix="/api/notebooks/{notebook_id}/chat", tags=["chat"])


@router.get("", response_model=List[ChatMessage])
async def get_chat_history(notebook_id: str):
    notebook = await get_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    messages = await get_messages(notebook_id)
    return [ChatMessage(**message) for message in messages]


@router.post("", response_model=ChatMessage)
async def send_message(
    notebook_id: str,
    req: ChatRequest,
    x_gemini_api_key: Optional[str] = Header(default=None, alias="X-Gemini-API-Key"),
):
    notebook = await get_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    await add_message(notebook_id, "user", req.message)
    sources = await get_sources(notebook_id)
    ready_sources = [source for source in sources if source.get("status") == "ready"]
    if not ready_sources:
        raise HTTPException(status_code=400, detail="No processed sources are ready yet")

    history = await get_messages(notebook_id)
    answer = await generate_answer(
        req.message,
        ready_sources,
        history,
        api_key=x_gemini_api_key,
    )
    message = await add_message(notebook_id, "assistant", answer["content"], answer["sources_cited"])
    return ChatMessage(**message)
