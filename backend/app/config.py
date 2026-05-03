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
    # Gemini access. The env-level key is optional — clients normally supply
    # their own via the X-Gemini-API-Key header (BYOK). Setting GEMINI_API_KEY
    # here just provides a fallback when no per-request key is sent.
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # Storage. Empty Supabase env → in-memory repository (single-process,
    # state lost on restart, fine for hobby/Render-style deploys).
    supabase_url: Optional[str] = os.getenv("SUPABASE_URL")
    supabase_key: Optional[str] = os.getenv("SUPABASE_KEY")

    # Crawling
    firecrawl_api_key: Optional[str] = os.getenv("FIRECRAWL_API_KEY")
    firecrawl_fallback_min_chars: int = int(os.getenv("FIRECRAWL_FALLBACK_MIN_CHARS", "200"))

    # CORS — set to the frontend origin in production.
    cors_origins: list[str] = field(
        default_factory=lambda: _split_csv(
            os.getenv("CORS_ORIGINS"),
            ["http://localhost:5173", "http://127.0.0.1:5173"],
        )
    )

    # Discovery + processing knobs
    max_discovery_results: int = int(os.getenv("MAX_DISCOVERY_RESULTS", "12"))
    max_document_chars: int = int(os.getenv("MAX_DOCUMENT_CHARS", "15000"))
    edge_similarity_threshold: float = float(os.getenv("EDGE_SIMILARITY_THRESHOLD", "0.05"))

    # Hard ceiling for the discovery+crawl+summarize phase. Anything still
    # in flight at this point is cancelled and its source marked errored,
    # so the user gets a usable notebook instead of waiting on the slow tail.
    notebook_crawl_deadline_s: float = float(os.getenv("NOTEBOOK_CRAWL_DEADLINE_S", "40"))

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
