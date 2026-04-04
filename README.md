# Synapse

Synapse is a research workspace that turns a single source into a connected body of knowledge. Start with a URL or a block of text, let Synapse discover and process related material, then explore the resulting graph and ask grounded questions against it.

## Overview

Most research tools either collect links or generate answers. Synapse does both, while keeping the source network visible.

With Synapse, you can:

- Start from one article, paper, note, or URL
- Discover related sources across the web
- Crawl, summarize, and embed each source
- Visualize how ideas connect in a source graph
- Chat with the notebook using retrieval grounded in processed sources

## Core Capabilities

### Source-Centered Research

Every notebook begins with a seed input and grows into a structured set of related sources instead of an opaque conversation thread.

### Knowledge Graph Exploration

Synapse maps relationships between sources so users can move from isolated documents to a broader understanding of a topic.

### Grounded Q&A

Chat responses are generated from retrieved notebook context, helping answers stay tied to the collected material.

### Flexible Runtime

The app supports a lightweight in-memory mode for local development and an optional Supabase-backed mode for persistence.

## How It Works

1. Create a notebook from a seed URL or pasted text.
2. Extract the topic and discover relevant related sources.
3. Crawl and process each source with summaries and embeddings.
4. Build source-to-source relationships as a graph.
5. Ask questions against the notebook's processed source base.

## Product Surface

- Seed input for creating notebooks from URLs or raw text
- Formation view showing notebook processing and graph assembly
- Source panel for navigating collected materials
- Graph view for exploring connections between sources
- Chat panel for grounded follow-up questions
- Demo mode for previewing the experience without backend services

## Architecture

- Frontend: React 19, Vite, Tailwind CSS 4, D3 force graph
- Backend: FastAPI, Celery, Redis
- AI layer: Gemini for discovery, title generation, summarization, embeddings, and grounded answers
- Crawling: `httpx`, `trafilatura`, optional Firecrawl fallback
- Storage: in-memory repository by default, optional Supabase persistence

## Repository Layout

```text
frontend/   React app, graph UI, chat panel, and demo mode
backend/    FastAPI API, worker pipeline, crawling, retrieval, and graph logic
docs/       Design notes and implementation plans
```

## Getting Started

### Quick Preview

To run the UI in demo mode without backend services or API keys:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173/?demo`.

### Local Development

#### Prerequisites

- Node.js 20+
- Python 3.11+
- Redis if you want to run Celery as a separate worker
- Gemini API key for live discovery, summarization, embeddings, and chat
- Optional: Supabase credentials for persistent storage
- Optional: Firecrawl API key for harder crawling cases and PDFs

#### 1. Configure environment

```bash
cp .env.example .env
```

Recommended local setup:

- Set `GEMINI_API_KEY`
- Leave `SUPABASE_URL` and `SUPABASE_KEY` blank to use the in-memory repository
- Keep `CELERY_TASK_ALWAYS_EAGER=true` for a single-process setup, or set it to `false` and run a worker separately

#### 2. Start the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 3. Start the worker

If `CELERY_TASK_ALWAYS_EAGER=true`, you can skip this step.

For the full async pipeline:

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

## Configuration

| Variable | Required | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | Yes for live AI features | Discovery, summaries, embeddings, and grounded chat |
| `FIRECRAWL_API_KEY` | No | Improved fallback crawling, especially for difficult pages and PDFs |
| `SUPABASE_URL` | No | Enables persistent storage instead of in-memory mode |
| `SUPABASE_KEY` | No | Auth key for Supabase access |
| `REDIS_URL` | No | Broker/backend for Celery, defaults to `redis://localhost:6379/0` |
| `CELERY_TASK_ALWAYS_EAGER` | No | Runs notebook processing inline for a simpler local setup |
| `CORS_ORIGINS` | No | Comma-separated allowed frontend origins |

## API

- `POST /api/notebooks` creates a notebook from a seed URL or text
- `GET /api/notebooks/:id` returns notebook state, sources, and edges
- `POST /api/notebooks/:id/sources` adds additional sources
- `GET /api/notebooks/:id/chat` returns chat history
- `POST /api/notebooks/:id/chat` asks a grounded question against processed sources
- `GET /api/health` reports app configuration status

## Roadmap

- Better source ranking and filtering
- Richer graph labeling and clustering
- Stronger persistence and collaboration workflows
- Better citation visibility inside answers
- Production deployment and hosted environments

## Security Note

This repository is set up so local secrets such as `.env`, local Claude settings, Redis dumps, virtual environments, and other machine-specific files are ignored by git. Use `.env.example` as the template for local configuration and keep real keys in your untracked `.env`.
