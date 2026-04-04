from __future__ import annotations

import importlib


def test_settings_parse_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "supabase-secret")
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/1")
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
    monkeypatch.setenv("MAX_DISCOVERY_RESULTS", "7")
    monkeypatch.setenv("MAX_DOCUMENT_CHARS", "1234")
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "true")

    config = importlib.import_module("app.config")
    importlib.reload(config)
    settings = config.get_settings()

    assert settings.has_gemini is True
    assert settings.has_supabase is True
    assert settings.redis_url == "redis://example:6379/1"
    assert settings.cors_origins == ["https://a.example", "https://b.example"]
    assert settings.max_discovery_results == 7
    assert settings.max_document_chars == 1234
    assert settings.celery_task_always_eager is True


def test_settings_defaults(monkeypatch):
    for key in [
        "GEMINI_API_KEY",
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "REDIS_URL",
        "CORS_ORIGINS",
        "MAX_DISCOVERY_RESULTS",
        "MAX_DOCUMENT_CHARS",
        "CELERY_TASK_ALWAYS_EAGER",
        "EDGE_SIMILARITY_THRESHOLD",
        "RAG_MAX_CHUNKS",
        "RAG_MAX_CHUNKS_PER_SOURCE",
        "EDGE_LABEL_BATCH_SIZE",
    ]:
        monkeypatch.delenv(key, raising=False)

    # Prevent load_dotenv() from restoring keys from the .env file during reload
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda **kwargs: None)

    config = importlib.import_module("app.config")
    importlib.reload(config)
    settings = config.get_settings()

    assert settings.has_gemini is False
    assert settings.has_supabase is False
    assert settings.redis_url == "redis://localhost:6379/0"
    assert "http://localhost:5173" in settings.cors_origins
