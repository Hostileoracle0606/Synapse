# Synapse

Synapse turns a single seed URL or block of text into a living research notebook. It discovers related sources, crawls and summarizes them, maps the relationships into a source graph, and lets you ask grounded questions against the resulting knowledge base.

Built for hackathon demos, Synapse is designed to feel fast, visual, and easy to explain:

- Start from one link or pasted note
- Auto-discover related sources across the web
- Build a knowledge graph showing how sources connect
- Chat with the notebook using source-grounded retrieval
- Run a frontend-only demo mode when you just need the pitch to work

## What It Does

Synapse helps researchers, students, founders, and judges go from "I have one interesting source" to "I understand the space" in minutes.

The workflow:

1. Seed the notebook with a URL or pasted text.
2. Extract the main topic and discover related sources.
3. Crawl and process each source with summaries and embeddings.
4. Build a relationship graph between the sources.
5. Ask questions and get answers grounded in the notebook's source set.

## Why It Feels Hackathon-Friendly

- Clear before/after story: one source becomes a navigable knowledge graph
- Strong visual moment: the formation screen animates the notebook as sources are discovered and connected
- Easy offline demo path: `?demo` mode runs without the backend
- Flexible architecture: works in-memory for local prototyping and with Supabase/Redis for a fuller setup

## Stack

- Frontend: React 19, Vite, Tailwind CSS 4, D3 force graph
- Backend: FastAPI, Celery, Redis
- AI: Gemini for title generation, source discovery, summarization, embeddings, and grounded answers
- Crawling: `httpx`, `trafilatura`, optional Firecrawl fallback
- Storage: in-memory repository by default, optional Supabase persistence

## Repo Layout

```text
frontend/   React app, graph UI, chat panel, and demo mode
backend/    FastAPI API, worker pipeline, crawling, retrieval, and graph logic
docs/       Planning/spec notes from development
```

## Quickstart

### Option 1: Frontend-only demo mode

This is the fastest way to show the project without any API keys or backend services.

```bash
cd frontend
npm install
npm run dev
```

Then open:

```text
http://localhost:5173/?demo
```

### Option 2: Full local app

#### Prerequisites

- Node.js 20+
- Python 3.11+
- Redis if you want a separate Celery worker
- Gemini API key for live AI-powered discovery and chat
- Optional: Supabase credentials for persistence
- Optional: Firecrawl API key for tougher crawling cases and PDFs

#### 1. Configure environment

```bash
cp .env.example .env
```

Recommended local hackathon setup:

- Set `GEMINI_API_KEY`
- Leave `SUPABASE_URL` and `SUPABASE_KEY` blank to use in-memory storage
- Keep `CELERY_TASK_ALWAYS_EAGER=true` if you want to avoid running a separate worker during local development

#### 2. Start the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 3. Start the worker

If `CELERY_TASK_ALWAYS_EAGER=true`, you can skip this step for quick local hacking.

If you want the full async pipeline:

```bash
cd backend
source .venv/bin/activate
PYTHONPATH=. celery -A app.worker.celery_app worker --loglevel=info
```

#### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` requests to `http://localhost:8000`.

## Environment Variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | Yes for live AI features | Discovery, summaries, embeddings, chat answers |
| `FIRECRAWL_API_KEY` | No | Better fallback crawling, especially for difficult pages and PDFs |
| `SUPABASE_URL` | No | Enables persistent storage instead of in-memory mode |
| `SUPABASE_KEY` | No | Auth key for Supabase access |
| `REDIS_URL` | No | Broker/backend for Celery, defaults to `redis://localhost:6379/0` |
| `CELERY_TASK_ALWAYS_EAGER` | No | Runs notebook processing inline for a simpler local setup |
| `CORS_ORIGINS` | No | Comma-separated allowed frontend origins |

## API Surface

- `POST /api/notebooks` creates a notebook from a seed URL or text
- `GET /api/notebooks/:id` returns notebook state, sources, and edges
- `POST /api/notebooks/:id/sources` adds extra sources
- `GET /api/notebooks/:id/chat` returns chat history
- `POST /api/notebooks/:id/chat` asks a grounded question against processed sources
- `GET /api/health` reports app configuration status

## How We Built It

The backend pipeline processes notebooks in stages:

1. Process the seed source
2. Discover related sources with Gemini
3. Crawl discovered pages concurrently
4. Summarize and embed sources in parallel
5. Build graph edges and relationship labels
6. Use chunk-aware retrieval for grounded chat answers

The frontend mirrors that journey with a formation screen, source list, graph view, and chat panel so users can understand what the notebook is doing in real time.

## Challenges

- Keeping the pipeline resilient when crawling quality varies across sites
- Supporting a useful local mode with optional infrastructure
- Making the graph feel alive enough for a demo, not just technically correct
- Balancing fast hackathon UX with a backend architecture that can grow

## What's Next

- Better source filtering and ranking
- Richer graph labels and clustering
- Stronger persistence and collaboration features
- Sharper citation UX inside answers
- One-click deployment for public demos

## Security Note

This repository is set up so local secrets such as `.env`, local Claude settings, Redis dumps, virtual environments, and other machine-specific files are ignored by git. Use `.env.example` as the template for local configuration and keep real keys in your untracked `.env`.
