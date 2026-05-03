# Synapse backend — single-stage Python image for Fly.io.
#
# Why python:3.13-slim:
#   - python:3.13 (full) is ~1GB; slim is ~150MB. Same Python, fewer
#     OS userland tools we don't need at runtime.
#   - All our deps (trafilatura, httpx, google-genai, etc.) ship pre-built
#     wheels for cp313 on linux/amd64, so we don't need a build toolchain.
#
# Why this Dockerfile is intentionally minimal:
#   - We don't run a separate worker process anymore (Celery is gone).
#   - There's no DB schema to migrate at startup (in-memory by default).
#   - There's no static-asset compile step (the React frontend is its
#     own deploy, on Cloudflare Workers).
# So the entire image is "Python + pip-installed deps + the app code."

FROM python:3.13-slim

# Sane defaults for Python in containers:
#   PYTHONDONTWRITEBYTECODE  — don't litter .pyc files in volume mounts
#   PYTHONUNBUFFERED         — flush stdout/stderr immediately so logs
#                              show up in `fly logs` without delay
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# Layer cache trick: copy *only* requirements.txt first, install deps,
# then copy the app code. Rebuilding when only app/ changes skips the
# expensive pip install step entirely (~30s saved per deploy).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Fly.io routes external traffic through its proxy to this internal
# port. fly.toml's [http_service].internal_port matches.
EXPOSE 8080

# `sh -c` is required so $PORT is interpolated. Fly sets PORT in the
# environment; we default to 8080 if running the image directly via
# `docker run`.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
