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
- [The Devpost story](#the-devpost-story)
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

## The Devpost story

### Inspiration

Most "AI research assistants" today flatten the work into a chat thread. You ask a question, get an answer, lose the trail. The answer might be grounded — but the *connections between sources* aren't.

Real research doesn't look like that. It looks like a network of papers cross-referencing each other, lectures explaining the papers, blog posts critiquing both. We wanted a tool where the **graph of how ideas connect** is the primary surface, with chat as a way to navigate it — not the other way around.

### What it does

Synapse turns a single URL into a navigable knowledge graph in under a minute.

You paste an article, paper, or video link. Synapse:

1. **Reads the seed** with the right parser for its type (trafilatura for HTML, Gemini for PDFs, YouTube captions API for videos)
2. **Discovers ~12 related sources** via three parallel grounded Gemini calls (articles, papers, videos) — guaranteeing a mix of source types instead of mostly webpages
3. **Crawls and summarizes each one in parallel** with a 40-second global deadline
4. **Builds a graph** where edges are weighted keyword overlap on titles + summaries
5. **Lets you chat with the entire corpus** — answers cite sources as `[Source N]`, and those references light up as halos on the corresponding graph nodes

The result: a notebook where the *shape of related material* is visible at a glance, and every answer is anchored to specific sources you can inspect.

### How we built it

**Frontend** is React 19 + Vite + Tailwind 4. The graph is rendered as SVG with d3-force handling layout. We use react-markdown for chat output (with custom components for citation pills) and lucide-react for icons. Tooling and styling were intentionally kept inside the design system rather than reaching for `@tailwindcss/typography` — every UI element is hand-styled to match the rest of the app.

**Backend** is FastAPI on Python 3.13. The notebook pipeline is built around `asyncio.gather`, `asyncio.wait` with timeouts, and bounded semaphores for the parallelism story. There's no separate worker process — `enqueue_notebook_processing` is a single `asyncio.create_task` call that spawns the pipeline as a background task while the HTTP response returns immediately.

**AI layer** is Gemini 2.5 Flash, used for four distinct purposes:
- Three parallel grounded discovery calls (articles, papers, videos) using the `google_search` tool
- Native PDF parsing via `inline_data` (no separate parser library)
- Tools-based ingest (`url_context` + `google_search`) for Twitter, Reddit, LinkedIn — sites that bot-block direct fetches
- Long-context chat: the full notebook corpus is packed into the prompt, with `url_context` available so the model can re-read sources at query time if needed

**Hosting** is Cloudflare Workers for the frontend (static-assets model) and Fly.io for the backend (Dockerfile + auto-stop microVM). The split was deliberate: Cloudflare excels at static, Python on Workers is too restrictive for our pipeline.

### Challenges we ran into

**The frozen-citations bug.** For weeks, citations on the graph would "stick" to whatever the first chat question returned. Subsequent questions seemingly didn't update the highlight. The root cause was a regex (`\[Source\s+(\d+)\]`) that only matched the simplest bracket form `[Source 1]` — Gemini's actual output uses `[Source 1, 2, 3]` or `[Source 1, Source 3]`, which the regex returned 0 matches for. A fallback then attributed the citation to the *first 3 sources unconditionally*, which looked identical between questions. Two interlocking bugs that masked each other; the fix was a more permissive bracket-aware parser plus removing the misleading fallback.

**YouTube videos timing out.** Gemini's video API takes 30–90 seconds per lecture-length video — well past our 40-second notebook deadline. We tried bumping the deadline (slowed everything else), tried `MEDIA_RESOLUTION_LOW` (helped marginally), tried the `VideoMetadata.end_offset` field (turns out it's in the SDK type definitions but not actually supported by the public API). Eventually pivoted to `youtube-transcript-api` as the primary path — fetches the official caption track in ~1 second — with the slow Gemini path as a fallback for caption-less videos.

**Vestigial code from architectural pivots.** Synapse went through two big rewrites — RAG to long-context grounding, and Celery to plain asyncio. Each pivot left behind hundreds of lines of dead code: chunk stores, embedding pipelines, Celery scaffolding, schema migrations for tables nobody used. A late-stage cleanup pass removed ~600 net lines and dropped two dependencies.

**The Cloudflare Workers / Python mismatch.** Originally planned to deploy everything to Cloudflare. Discovered that Workers Python is Pyodide-based with a 30s execution cap, no thread pool, and no support for our `httpx` SSL-context pattern. Pivoted the backend to Fly.io and accepted the architectural split — frontend on Cloudflare for edge speed, backend on Fly.io for full Python.

### Accomplishments we're proud of

- **Sub-60-second pipeline.** Discovery + parallel crawl + summarize + graph for ~10 sources in ~50 seconds.
- **True multi-modal sources.** A single notebook can mix arXiv PDFs, YouTube lectures, news articles, Reddit threads, Twitter posts. Each routed to the right ingest path.
- **The graph is the UI.** Chat answers literally light up the cited nodes — the graph isn't decoration, it's how you navigate the corpus.
- **Cleanup passed.** ~600 LOC of vestigial code removed; the codebase is now smaller than it was 2 weeks ago despite shipping more features.
- **Live deploy on free tiers.** $0/month at hobby usage, frontend at the edge globally, backend cold-starts in 5–10 seconds.

### What we learned

- **Long-context grounding can replace RAG for small corpora** — and the grounding is *stronger* because the model sees full articles instead of retrieved chunks. RAG's complexity is justified when the corpus doesn't fit in context. Our notebooks always fit.
- **Per-platform deployment assumptions matter.** Cloudflare Workers' "every byte runs at the edge" model fundamentally conflicts with our 60-second async pipelines. Fly.io's "Firecracker microVMs that auto-sleep" model fits perfectly. There's no universally-best cloud — you pick based on what your workload looks like.
- **Don't trust SDK type hints alone.** The `VideoMetadata.end_offset` example was a sharp reminder that having a field in `Optional[str]` annotations doesn't mean the API supports it. Test against the live API.
- **Vestigial code accretes faster than you think.** Every architectural pivot left a residue. Quarterly cleanup passes catch them; without that, the codebase grows scarier even as features land.

### What's next for Synapse

- **Multi-notebook UX.** Today each session creates one notebook stored in memory. Support persistent multi-notebook libraries via Supabase.
- **Audio sources.** Add `gemini_ingest_audio` for podcasts and lectures via Gemini's native audio understanding (same pattern as PDFs).
- **Source caching.** SHA256 of normalized text → cached summary + content. Repeat-source hit rate would be high across notebooks on related topics.
- **Citation precision.** Today citations are at source-granularity. Adding chunk-level citation extraction would let the chat answer underline specific quoted sentences.
- **Export.** PNG of the graph; markdown export of the chat history with inline citations; bundled `.json` of the whole notebook for sharing.

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
