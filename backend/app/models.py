from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class CreateNotebookRequest(BaseModel):
    seed_url: Optional[str] = None
    seed_text: Optional[str] = None
    title: Optional[str] = None

    @model_validator(mode="after")
    def validate_seed(self) -> "CreateNotebookRequest":
        if not self.seed_url and not self.seed_text:
            raise ValueError("Provide seed_url or seed_text")
        return self


class AddSourceRequest(BaseModel):
    url: str
    title: Optional[str] = None
    source_type: str = "webpage"


class SourceResponse(BaseModel):
    id: str
    notebook_id: Optional[str] = None
    url: Optional[str] = None
    title: str
    source_type: str
    summary: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    content: Optional[str] = None
    created_at: Optional[datetime] = None


class EdgeResponse(BaseModel):
    id: Optional[str] = None
    source_a: str
    source_b: str
    similarity: float
    relationship: Optional[str] = None


class NotebookResponse(BaseModel):
    id: str
    title: str
    seed_url: Optional[str] = None
    seed_text: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    sources: List[SourceResponse] = Field(default_factory=list)
    edges: List[EdgeResponse] = Field(default_factory=list)


class NotebookCreateResponse(BaseModel):
    id: str
    title: str
    status: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class ChatMessage(BaseModel):
    id: Optional[str] = None
    notebook_id: Optional[str] = None
    role: str
    content: str
    sources_cited: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
