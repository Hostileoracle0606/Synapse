from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()


def _split_csv(value: Optional[str], default: List[str]) -> List[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    supabase_url: Optional[str] = os.getenv("SUPABASE_URL")
    supabase_key: Optional[str] = os.getenv("SUPABASE_KEY")
    firecrawl_api_key: Optional[str] = os.getenv("FIRECRAWL_API_KEY")
    firecrawl_fallback_min_chars: int = int(os.getenv("FIRECRAWL_FALLBACK_MIN_CHARS", "200"))
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_embed_model: str = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "768"))
    cors_origins: list[str] = field(
        default_factory=lambda: _split_csv(
            os.getenv("CORS_ORIGINS"),
            ["http://localhost:5173", "http://127.0.0.1:5173"],
        )
    )
    max_discovery_results: int = int(os.getenv("MAX_DISCOVERY_RESULTS", "15"))
    max_document_chars: int = int(os.getenv("MAX_DOCUMENT_CHARS", "15000"))
    celery_task_always_eager: bool = os.getenv("CELERY_TASK_ALWAYS_EAGER", "").lower() in {
        "1",
        "true",
        "yes",
    }
    edge_similarity_threshold: float = float(os.getenv("EDGE_SIMILARITY_THRESHOLD", "0.4"))
    rag_max_chunks: int = int(os.getenv("RAG_MAX_CHUNKS", "8"))
    rag_max_chunks_per_source: int = int(os.getenv("RAG_MAX_CHUNKS_PER_SOURCE", "2"))
    edge_label_batch_size: int = int(os.getenv("EDGE_LABEL_BATCH_SIZE", "20"))

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
