from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from app.database import create_notebook, get_edges, get_notebook, get_sources
from app.models import (
    CreateNotebookRequest,
    EdgeResponse,
    NotebookCreateResponse,
    NotebookResponse,
    SourceResponse,
)
from app.services.crawler import smart_crawl_url
from app.services.discovery import extract_seed_title
from app.worker import enqueue_notebook_processing

router = APIRouter(prefix="/api/notebooks", tags=["notebooks"])


@router.post("", response_model=NotebookCreateResponse)
async def create_notebook_endpoint(
    req: CreateNotebookRequest,
    x_gemini_api_key: Optional[str] = Header(default=None, alias="X-Gemini-API-Key"),
):
    seed_text = req.seed_text
    title = req.title

    if req.seed_url:
        crawled = await smart_crawl_url(req.seed_url, api_key=x_gemini_api_key)
        if not crawled:
            raise HTTPException(status_code=400, detail="Could not fetch the provided URL")
        seed_text = crawled["text"]
        title = title or crawled["title"]
    elif not seed_text:
        raise HTTPException(status_code=400, detail="Provide seed_url or seed_text")

    title = title or await extract_seed_title(seed_text or "", api_key=x_gemini_api_key)
    notebook = await create_notebook(title=title, seed_url=req.seed_url, seed_text=seed_text)
    enqueue_notebook_processing(notebook["id"], seed_text or "", api_key=x_gemini_api_key)

    return NotebookCreateResponse(
        id=notebook["id"],
        title=notebook["title"],
        status=notebook["status"],
    )


@router.get("/{notebook_id}", response_model=NotebookResponse)
async def get_notebook_endpoint(notebook_id: str):
    notebook = await get_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    sources = await get_sources(notebook_id)
    edges = await get_edges(notebook_id)
    return NotebookResponse(
        **notebook,
        sources=[SourceResponse(**source) for source in sources],
        edges=[EdgeResponse(**edge) for edge in edges],
    )
