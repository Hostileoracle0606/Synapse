import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import chat, notebooks, sources
from app.worker import celery_app

# ── Logging setup ────────────────────────────────────────────────────────────
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=_LOG_FORMAT,
    datefmt=_DATE_FORMAT,
    stream=sys.stdout,
    force=True,  # override any prior basicConfig calls
)

# Silence spammy third-party loggers, keep ours verbose
for _noisy in ("httpx", "httpcore", "hpack"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

settings = get_settings()
app = FastAPI(title="Synapse API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(notebooks.router)
app.include_router(sources.router)
app.include_router(chat.router)
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


@app.on_event("startup")
async def _on_startup():
    repo_type = "Supabase" if settings.has_supabase else "in-memory"
    logger.info(
        "Synapse API starting — gemini=%s  repo=%s  redis=%s  embed_dim=%d  edge_threshold=%.2f",
        settings.has_gemini,
        repo_type,
        settings.redis_url,
        settings.embedding_dimension,
        settings.edge_similarity_threshold,
    )


class _RequestLogger(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        t0 = time.monotonic()
        response = await call_next(request)
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "%s %s → %d  (%.0fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response


app.add_middleware(_RequestLogger)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "services": {
            "gemini_configured": settings.has_gemini,
            "supabase_configured": settings.has_supabase,
            "redis_url": settings.redis_url,
        },
    }


@app.get("/health")
async def health_simple():
    try:
        celery_app.control.ping(timeout=2.0)
        celery_status = "ok"
    except Exception:
        celery_status = "unavailable"
    return {"status": "ok", "celery": celery_status}
