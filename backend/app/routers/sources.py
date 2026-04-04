from typing import List

from fastapi import APIRouter, HTTPException

from app.database import create_source, get_notebook, get_sources
from app.models import AddSourceRequest, SourceResponse

router = APIRouter(prefix="/api/notebooks/{notebook_id}/sources", tags=["sources"])


@router.get("", response_model=List[SourceResponse])
async def list_sources(notebook_id: str):
    sources = await get_sources(notebook_id)
    return [SourceResponse(**source) for source in sources]


@router.post("", response_model=SourceResponse)
async def add_source(notebook_id: str, req: AddSourceRequest):
    notebook = await get_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    source = await create_source(
        notebook_id=notebook_id,
        url=req.url,
        title=req.title or req.url,
        source_type=req.source_type,
    )
    return SourceResponse(**source)
