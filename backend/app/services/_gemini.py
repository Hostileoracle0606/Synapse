from __future__ import annotations

from functools import lru_cache
from typing import Optional

from app.config import get_settings


@lru_cache(maxsize=1)
def _load_genai():
    try:
        from google import genai
        from google.genai import types
    except Exception:  # pragma: no cover - dependency may not be installed yet
        return None, None
    return genai, types


def _resolve_api_key(api_key: Optional[str]) -> Optional[str]:
    """Pick the per-request key if provided, otherwise fall back to env settings."""
    if api_key and api_key.strip():
        return api_key.strip()
    settings = get_settings()
    return settings.gemini_api_key or None


def get_genai_client(api_key: Optional[str] = None):
    """Return a Gemini client bound to either the per-request key or the env key.

    Returns None if neither key is available or the SDK isn't importable.
    """
    resolved = _resolve_api_key(api_key)
    if not resolved:
        return None
    genai, _ = _load_genai()
    if genai is None:
        return None
    return genai.Client(api_key=resolved)


def get_genai_types():
    _, types = _load_genai()
    return types


def has_gemini(api_key: Optional[str] = None) -> bool:
    return bool(_resolve_api_key(api_key))
