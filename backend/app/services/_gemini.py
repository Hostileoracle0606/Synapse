from __future__ import annotations

from functools import lru_cache

from app.config import get_settings


@lru_cache(maxsize=1)
def _load_genai():
    try:
        from google import genai
        from google.genai import types
    except Exception:  # pragma: no cover - dependency may not be installed yet
        return None, None
    return genai, types


def get_genai_client():
    settings = get_settings()
    if not settings.has_gemini:
        return None
    genai, _ = _load_genai()
    if genai is None:
        return None
    return genai.Client(api_key=settings.gemini_api_key)


def get_genai_types():
    _, types = _load_genai()
    return types
