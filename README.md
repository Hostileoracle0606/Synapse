<div align="center">

# Synapse

**Turn one URL into a navigable knowledge graph.**

Synapse takes a single seed — an article, paper, video — and builds a multi-modal source graph around it. Discover, read, summarize, and chat with a curated body of research in under a minute.

[Live demo](https://synapse.trigo.workers.dev) · [Report bug](https://github.com/Hostileoracle0606/Synapse/issues) · [Request feature](https://github.com/Hostileoracle0606/Synapse/issues)

![Status](https://img.shields.io/badge/status-live-success)
![Frontend](https://img.shields.io/badge/frontend-Cloudflare%20Workers-F38020?logo=cloudflare&logoColor=white)
![Backend](https://img.shields.io/badge/backend-Fly.io-7B3F98?logo=flydotio&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-blue)

</div>

---

## Table of contents

- [What it does](#what-it-does)
- [How it works](#how-it-works)
- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Deployment](#deployment)
- [Project structure](#project-structure)
- [License](#license)

---

## What it does

Most research tools either *collect links* or *generate answers*. Synapse does both, while keeping the network of ideas visible.

| | |
|---|---|
| **Seed in any URL** | Wikipedia article, arXiv paper, YouTube lecture, blog post |
| **Multi-modal discovery** | Three parallel grounded calls fan out to surface articles, papers (PDFs), and videos in one pass |
| **Native ingestion per modality** | trafilatura for HTML, Gemini for PDFs, YouTube's caption API for videos, Gemini's `url_context` tool for Twitter/Reddit/LinkedIn |
| **Long-context grounded chat** | The full notebook corpus is loaded as context — citations are extracted from the answer and highlighted directly on the graph |
| **BYOK (Bring Your Own Key)** | Users provide their own Gemini API key. Backend never persists keys. |
| **Sub-60s pipeline** | Discovery + crawl + summarization + graph in ~50 seconds for ~10 sources |

## How it works

```
                    ┌──────────────────────────────────────────────────────┐
                    │                   Frontend (React)                   │
                    │   SeedInput → FormationScreen → Graph + Chat panel   │
                    │              Cloudflare Workers (edge)               │
                    └────────────────────────────┬─────────────────────────┘
                                                 │ /api/* (BYOK header)
                    ┌────────────────────────────▼─────────────────────────┐
                    │                  Backend (FastAPI)                   │
                    │                       Fly.io (iad)                   │
                    └────────────────────────────┬─────────────────────────┘
                                                 │ asyncio.create_task
                    ┌────────────────────────────▼─────────────────────────┐
                    │                  Pipeline (per notebook)             │
                    │                                                      │
                    │  ┌────────────┐    ┌────────────┐    ┌────────────┐  │
                    │  │  Stage 1+2 │ →  │  Stage 3+4 │ →  │   Stage 5  │  │
                    │  │            │    │            │    │            │  │
                    │  │  • seed    │    │ streaming  │    │  keyword-  │  │
                    │  │  • 3-call  │    │  crawl +   │    │  overlap   │  │
                    │  │  discovery │    │ summarize  │    │   edges    │  │
                    │  │ (parallel) │    │ (40s cap)  │    │  (no LLM)  │  │
                    │  └────────────┘    └────────────┘    └────────────┘  │
                    └──────────────────────────────────────────────────────┘
                                                 │
                                                 ▼
                                       Gemini 2.5 Flash
                                  (discovery, ingest, chat)
```

### Key architectural decisions

**Long-context grounding over RAG.** With 1M-token context windows, embedding + chunk retrieval is overkill for a single notebook of ~10 sources. The full corpus fits in the prompt, citations come back inline, and grounding is *stronger* than RAG because the model sees the whole article instead of 3 retrieved chunks.

**Three-call type-scoped discovery.** A single grounded call returns mostly web articles (Google's organic ranker dominates). Three parallel calls — one each for articles, papers, and videos — guarantee a mixed source set. Wall-clock is bounded by the slowest call, not summed.

**Streamed crawl→summarize with a global deadline.** Each source goes through crawl→summarize as a single async task. A global 40-second deadline cancels in-flight work so one slow PDF doesn't stall the whole notebook. Sources that finish make it; the rest are skipped silently.

**Multi-modal ingest, modality-aware routing:**
- **Webpages** → trafilatura (free, ~50ms, verbatim text extraction)
- **PDFs** → Gemini's native PDF parser via inline_data (extracts full text including tables)
- **YouTube** → `youtube-transcript-api` for ~1s caption fetch + YouTube oEmbed for title; falls back to Gemini's video file_uri for caption-less videos
- **Twitter / Reddit / LinkedIn** → Gemini's `url_context` + `google_search` tools (the only way to read content these sites bot-block)

**Async, in-process worker.** No Celery, no Redis, no separate worker process. The pipeline runs as `asyncio.create_task` on FastAPI's event loop — POST `/api/notebooks` returns in <100ms, the work happens in the background, and the in-memory repository is shared with no IPC overhead.

**Citation pills as graph highlights.** When the chat returns an answer, it cites sources as `[Source N]`. The frontend extracts those references and lights up the corresponding nodes in the graph with a pulsing halo, instead of dumping a separate "cited sources" list at the bottom of the message.

## Tech stack

<table>
<tr><td><b>Frontend</b></td><td>React 19 · Vite 6 · Tailwind CSS 4 · d3-force · react-markdown · lucide-react</td></tr>
<tr><td><b>Backend</b></td><td>FastAPI · Python 3.13 · asyncio · httpx · trafilatura · google-genai · youtube-transcript-api</td></tr>
<tr><td><b>AI layer</b></td><td>Gemini 2.5 Flash with <code>google_search</code>, <code>url_context</code>, native PDF + video understanding</td></tr>
<tr><td><b>Storage</b></td><td>In-memory by default (single-process). Optional Supabase for persistence.</td></tr>
<tr><td><b>Hosting</b></td><td>Cloudflare Workers (frontend) + Fly.io (backend) — together $0–2/month at hobby usage</td></tr>
</table>

## Quick start

### Prerequisites

- Node.js 20+
- Python 3.13+
- A free Gemini API key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

### Run locally

```bash
# Clone
git clone https://github.com/Hostileoracle0606/Synapse.git
cd Synapse

# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (in a second terminal)
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173), paste your Gemini API key into the BYOK field, and seed a URL.

### Demo mode (no backend, no key)

```bash
cd frontend && npm run dev
```

Open [http://localhost:5173/?demo](http://localhost:5173/?demo) — the UI runs against a static mock so you can explore the experience without spinning up the backend.

## Deployment

The deployment story is intentionally split: **frontend on Cloudflare's edge, backend on Fly.io's compute**. They live independently, talk over HTTPS, and together cost about $0/month at hobby scale.

### Frontend → Cloudflare Workers

```bash
cd frontend
VITE_API_BASE=https://your-backend.fly.dev npm run build
npx wrangler login    # one-time
npx wrangler deploy
```

The built static bundle (~140 KB gzipped) ships to Cloudflare's 300+ edge locations. Configuration lives in [`frontend/wrangler.toml`](frontend/wrangler.toml).

### Backend → Fly.io

```bash
cd backend
fly auth login        # one-time
fly launch --copy-config
fly secrets set CORS_ORIGINS=https://your-frontend.workers.dev
fly deploy
```

`Dockerfile` is single-stage (~150 MB final image), `fly.toml` configures auto-stop / auto-start so the machine sleeps when idle (~$0/month) and wakes in ~5–10 seconds on the first request after sleep.

### Optional: Supabase persistence

By default the backend uses an in-memory repository — state is lost on restart, fine for hobby/single-user. Set `SUPABASE_URL` + `SUPABASE_KEY` env vars and run [`supabase_schema.sql`](backend/supabase_schema.sql) in your Supabase project to switch to persistent Postgres-backed storage.

## Project structure

```
.
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI app + CORS + health
│   │   ├── config.py                   # Settings (env-driven)
│   │   ├── database.py                 # In-memory + Supabase repos
│   │   ├── worker.py                   # Async pipeline (no Celery)
│   │   ├── routers/                    # /api/notebooks, /api/sources, /api/chat
│   │   └── services/
│   │       ├── crawler.py              # Type-aware routing + trafilatura
│   │       ├── discovery.py            # 3-call type-scoped fan-out
│   │       ├── gemini_ingest.py        # PDF, YouTube, tools-based ingest
│   │       ├── processor.py            # Summarization
│   │       ├── graph.py                # Keyword-overlap edge computation
│   │       └── rag.py                  # Long-context grounded chat
│   ├── Dockerfile                      # Production image for Fly.io
│   ├── fly.toml                        # Fly.io app config
│   └── supabase_schema.sql             # Optional persistent schema
├── frontend/
│   ├── src/
│   │   ├── App.jsx                     # State machine: seed → formation → main
│   │   ├── api.js                      # Backend client (with BYOK header)
│   │   ├── apiKey.js                   # localStorage-backed key helper
│   │   ├── mockApi.js                  # ?demo mode mock
│   │   └── components/
│   │       ├── SeedInput.jsx           # Initial URL + API key entry
│   │       ├── FormationScreen.jsx     # The "watch the graph form" experience
│   │       ├── DocumentWeb.jsx         # The main interactive graph
│   │       ├── SourcesPanel.jsx        # Expandable source cards
│   │       ├── ChatPanel.jsx           # Resizable chat with markdown
│   │       ├── MarkdownContent.jsx     # Citation pills inside chat output
│   │       └── Header.jsx              # Top-bar with API key chip
│   ├── wrangler.toml                   # Cloudflare Workers config
│   └── vite.config.js
├── LICENSE
└── README.md
```

## License

[MIT](LICENSE) — do whatever you want with this, just don't blame us.

---

<div align="center">

**[⬆ back to top](#synapse)**

</div>
