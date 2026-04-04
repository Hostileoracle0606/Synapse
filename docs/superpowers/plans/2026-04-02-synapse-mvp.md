# Synapse Notebook MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working MVP where a user pastes a URL or uploads a document, the system auto-discovers related sources via Gemini + Google Search grounding, builds a document web graph, and lets the user chat with the knowledge base.

**Architecture:** FastAPI backend handles discovery, crawling, and AI. React frontend (existing UI) connects via REST API. Supabase provides Postgres + pgvector for storage. Gemini 2.5 Flash powers discovery, summarization, and chat. Gemini Search Grounding finds related sources. `gemini-embedding-001` computes document similarity for graph edges.

**Tech Stack:**
- **Frontend:** React + Vite + Tailwind CSS + d3-force (graph)
- **Backend:** FastAPI (Python 3.11+), google-genai SDK, Celery + Redis (async tasks)
- **AI:** Gemini 2.5 Flash (generation), gemini-embedding-001 (embeddings), Google Search Grounding (discovery)
- **Storage:** Supabase (Postgres + pgvector + Auth + File Storage)
- **Crawling:** Trafilatura (HTML text extraction), httpx (async HTTP)
- **Deploy:** Vercel (frontend) + Railway (backend + Redis)

---

## File Structure

```
Synapse/
├── frontend/                    # React app (move existing src/ here)
│   ├── src/
│   │   ├── App.jsx              # Root layout + routing
│   │   ├── main.jsx             # Vite entry point
│   │   ├── api.js               # API client (fetch wrapper to backend)
│   │   ├── components/
│   │   │   ├── Header.jsx       # Top nav bar
│   │   │   ├── SourcesPanel.jsx # Left column: source list + upload
│   │   │   ├── DocumentWeb.jsx  # Center: d3-force document graph
│   │   │   ├── NodePopover.jsx  # Popover card for clicked document node
│   │   │   ├── ChatPanel.jsx    # Right column: notebook guide chat
│   │   │   └── SeedInput.jsx    # Initial seed URL/file input modal
│   │   └── hooks/
│   │       ├── useNotebook.js   # State management for current notebook
│   │       └── useChat.js       # Chat messages state + streaming
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + CORS + routes
│   │   ├── config.py            # Environment variables + settings
│   │   ├── models.py            # Pydantic models (request/response schemas)
│   │   ├── database.py          # Supabase client + DB queries
│   │   ├── routers/
│   │   │   ├── notebooks.py     # POST /notebooks, GET /notebooks/:id
│   │   │   ├── sources.py       # GET /notebooks/:id/sources, POST manual add
│   │   │   └── chat.py          # POST /notebooks/:id/chat (streaming)
│   │   ├── services/
│   │   │   ├── discovery.py     # Gemini Search Grounding → find related URLs
│   │   │   ├── crawler.py       # Fetch URL → extract text via trafilatura
│   │   │   ├── processor.py     # Summarize + embed documents via Gemini
│   │   │   ├── graph.py         # Compute document similarity → edges
│   │   │   └── rag.py           # Retrieve relevant chunks + generate answer
│   │   └── worker.py            # Celery task definitions
│   ├── requirements.txt
│   ├── Procfile                 # Railway deploy config
│   └── .env.example
├── docs/
│   └── superpowers/plans/
│       └── 2026-04-02-synapse-mvp.md
└── .gitignore
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.js`, `frontend/tailwind.config.js`, `frontend/index.html`, `frontend/src/main.jsx`
- Move: `src/App.jsx` → `frontend/src/App.jsx`
- Create: `backend/requirements.txt`, `backend/app/main.py`, `backend/app/config.py`
- Create: `.gitignore`, `.env.example`

- [ ] **Step 1: Initialize frontend with Vite**

```bash
cd /Users/trinabgoswamy/Synapse
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm install -D tailwindcss @tailwindcss/vite
npm install lucide-react d3-force
```

- [ ] **Step 2: Configure Tailwind for Vite**

Replace `frontend/vite.config.js`:
```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
```

Replace `frontend/src/index.css`:
```css
@import "tailwindcss";
```

- [ ] **Step 3: Move existing App.jsx into frontend/src/**

```bash
cp /Users/trinabgoswamy/Synapse/src/App.jsx /Users/trinabgoswamy/Synapse/frontend/src/App.jsx
```

Remove the old `src/` directory.

- [ ] **Step 4: Verify frontend runs**

```bash
cd /Users/trinabgoswamy/Synapse/frontend
npm run dev
```

Expected: App renders at http://localhost:5173 with existing UI.

- [ ] **Step 5: Initialize backend**

```bash
mkdir -p /Users/trinabgoswamy/Synapse/backend/app/routers
mkdir -p /Users/trinabgoswamy/Synapse/backend/app/services
```

Create `backend/requirements.txt`:
```
fastapi==0.115.0
uvicorn==0.30.0
google-genai==1.5.0
supabase==2.9.0
httpx==0.27.0
trafilatura==1.12.0
celery[redis]==5.4.0
python-dotenv==1.0.1
numpy==2.1.0
```

Create `backend/app/config.py`:
```python
from dotenv import load_dotenv
import os

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_EMBED_MODEL = "gemini-embedding-001"
```

Create `backend/app/main.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Synapse API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Verify backend runs**

```bash
cd /Users/trinabgoswamy/Synapse/backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Expected: `GET http://localhost:8000/api/health` returns `{"status": "ok"}`

- [ ] **Step 7: Create .gitignore and .env.example**

`.gitignore`:
```
node_modules/
dist/
__pycache__/
*.pyc
.env
.venv/
venv/
```

`.env.example`:
```
GEMINI_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
REDIS_URL=redis://localhost:6379/0
```

- [ ] **Step 8: Commit**

```bash
git init
git add .
git commit -m "feat: scaffold frontend (Vite+React+Tailwind) and backend (FastAPI)"
```

---

## Task 2: Database Schema (Supabase)

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/supabase_schema.sql` (reference, run in Supabase dashboard)

- [ ] **Step 1: Write the SQL schema**

Create `backend/supabase_schema.sql`:
```sql
-- Enable pgvector extension
create extension if not exists vector;

-- Notebooks (one per seed)
create table notebooks (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  seed_url text,
  seed_text text,
  status text not null default 'discovering', -- discovering | ready | error
  created_at timestamptz default now()
);

-- Discovered sources/documents
create table sources (
  id uuid primary key default gen_random_uuid(),
  notebook_id uuid references notebooks(id) on delete cascade,
  url text,
  title text not null,
  source_type text not null default 'webpage', -- webpage | pdf | seed
  summary text,
  content text,
  embedding vector(768),
  status text not null default 'pending', -- pending | crawling | processing | ready | error
  error_message text,
  created_at timestamptz default now()
);

-- Precomputed document-to-document edges
create table edges (
  id uuid primary key default gen_random_uuid(),
  notebook_id uuid references notebooks(id) on delete cascade,
  source_a uuid references sources(id) on delete cascade,
  source_b uuid references sources(id) on delete cascade,
  similarity float not null,
  relationship text, -- AI-generated label: "both discuss transformer architectures"
  unique(source_a, source_b)
);

-- Chat messages
create table messages (
  id uuid primary key default gen_random_uuid(),
  notebook_id uuid references notebooks(id) on delete cascade,
  role text not null, -- user | assistant
  content text not null,
  sources_cited uuid[], -- array of source IDs referenced in response
  created_at timestamptz default now()
);

-- Index for vector similarity search
create index on sources using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- Index for notebook lookups
create index on sources (notebook_id);
create index on edges (notebook_id);
create index on messages (notebook_id);
```

- [ ] **Step 2: Run schema in Supabase**

Go to Supabase Dashboard → SQL Editor → paste and run the SQL above.

- [ ] **Step 3: Write database.py**

Create `backend/app/database.py`:
```python
from supabase import create_client
from app.config import SUPABASE_URL, SUPABASE_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


async def create_notebook(title: str, seed_url: str = None, seed_text: str = None):
    result = supabase.table("notebooks").insert({
        "title": title,
        "seed_url": seed_url,
        "seed_text": seed_text,
        "status": "discovering",
    }).execute()
    return result.data[0]


async def get_notebook(notebook_id: str):
    result = supabase.table("notebooks").select("*").eq("id", notebook_id).single().execute()
    return result.data


async def update_notebook_status(notebook_id: str, status: str):
    supabase.table("notebooks").update({"status": status}).eq("id", notebook_id).execute()


async def create_source(notebook_id: str, url: str, title: str, source_type: str = "webpage"):
    result = supabase.table("sources").insert({
        "notebook_id": notebook_id,
        "url": url,
        "title": title,
        "source_type": source_type,
        "status": "pending",
    }).execute()
    return result.data[0]


async def update_source(source_id: str, **fields):
    supabase.table("sources").update(fields).eq("id", source_id).execute()


async def get_sources(notebook_id: str):
    result = supabase.table("sources").select("*").eq("notebook_id", notebook_id).order("created_at").execute()
    return result.data


async def create_edge(notebook_id: str, source_a: str, source_b: str, similarity: float, relationship: str):
    supabase.table("edges").insert({
        "notebook_id": notebook_id,
        "source_a": source_a,
        "source_b": source_b,
        "similarity": similarity,
        "relationship": relationship,
    }).execute()


async def get_edges(notebook_id: str):
    result = supabase.table("edges").select("*").eq("notebook_id", notebook_id).execute()
    return result.data


async def get_sources_with_embeddings(notebook_id: str):
    result = supabase.table("sources").select("id, title, embedding").eq("notebook_id", notebook_id).eq("status", "ready").execute()
    return result.data


async def add_message(notebook_id: str, role: str, content: str, sources_cited: list = None):
    result = supabase.table("messages").insert({
        "notebook_id": notebook_id,
        "role": role,
        "content": content,
        "sources_cited": sources_cited or [],
    }).execute()
    return result.data[0]


async def get_messages(notebook_id: str):
    result = supabase.table("messages").select("*").eq("notebook_id", notebook_id).order("created_at").execute()
    return result.data
```

- [ ] **Step 4: Write test to verify DB connection**

Create `backend/tests/test_db.py`:
```python
import pytest
from app.database import supabase


def test_supabase_connection():
    """Verify we can reach Supabase and the notebooks table exists."""
    result = supabase.table("notebooks").select("id").limit(1).execute()
    assert result.data is not None  # Empty list is fine, just not an error
```

- [ ] **Step 5: Run test**

```bash
cd /Users/trinabgoswamy/Synapse/backend
PYTHONPATH=. pytest tests/test_db.py -v
```

Expected: PASS (assuming .env is configured with Supabase credentials)

- [ ] **Step 6: Commit**

```bash
git add backend/supabase_schema.sql backend/app/database.py backend/tests/test_db.py
git commit -m "feat: add Supabase schema and database access layer"
```

---

## Task 3: Pydantic Models

**Files:**
- Create: `backend/app/models.py`

- [ ] **Step 1: Define request/response schemas**

Create `backend/app/models.py`:
```python
from pydantic import BaseModel
from typing import Optional


class CreateNotebookRequest(BaseModel):
    seed_url: Optional[str] = None
    seed_text: Optional[str] = None
    title: Optional[str] = None


class SourceResponse(BaseModel):
    id: str
    url: Optional[str]
    title: str
    source_type: str
    summary: Optional[str]
    status: str
    error_message: Optional[str]


class EdgeResponse(BaseModel):
    source_a: str
    source_b: str
    similarity: float
    relationship: Optional[str]


class NotebookResponse(BaseModel):
    id: str
    title: str
    status: str
    sources: list[SourceResponse] = []
    edges: list[EdgeResponse] = []


class ChatRequest(BaseModel):
    message: str


class ChatMessage(BaseModel):
    role: str
    content: str
    sources_cited: list[str] = []
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models.py
git commit -m "feat: add Pydantic request/response models"
```

---

## Task 4: Discovery Service (Gemini Search Grounding)

**Files:**
- Create: `backend/app/services/discovery.py`
- Create: `backend/tests/test_discovery.py`

This is the core of the product. Given a seed document's content, we ask Gemini with Google Search grounding to find related sources. Gemini returns grounding chunks with real URLs.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_discovery.py`:
```python
import pytest
from app.services.discovery import discover_related_sources


@pytest.mark.asyncio
async def test_discover_returns_urls():
    """Given seed text about AI, discovery should return a list of URLs with titles."""
    seed_text = "Neural networks are transforming healthcare diagnostics through deep learning approaches to medical imaging."
    results = await discover_related_sources(seed_text, max_results=5)

    assert isinstance(results, list)
    assert len(results) > 0
    for result in results:
        assert "url" in result
        assert "title" in result
        assert result["url"].startswith("http")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/trinabgoswamy/Synapse/backend
PYTHONPATH=. pytest tests/test_discovery.py -v
```

Expected: FAIL — `discover_related_sources` does not exist yet.

- [ ] **Step 3: Implement discovery service**

Create `backend/app/services/discovery.py`:
```python
from google import genai
from google.genai import types
from app.config import GEMINI_API_KEY, GEMINI_MODEL

client = genai.Client(api_key=GEMINI_API_KEY)


async def discover_related_sources(seed_text: str, max_results: int = 15) -> list[dict]:
    """Use Gemini with Google Search grounding to find related sources.

    Returns a list of {"url": ..., "title": ...} dicts.
    """
    prompt = f"""Based on the following text, find related and authoritative sources
on the web that cover the same topics, provide additional context, or offer
different perspectives. Return diverse source types: research papers, news articles,
technical blogs, official documentation, and reports.

TEXT:
{seed_text[:4000]}

Find {max_results} highly relevant sources."""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )

    # Extract grounding chunks (real URLs returned by Google Search)
    sources = []
    seen_urls = set()

    if response.candidates and response.candidates[0].grounding_metadata:
        metadata = response.candidates[0].grounding_metadata
        if metadata.grounding_chunks:
            for chunk in metadata.grounding_chunks:
                if chunk.web and chunk.web.uri and chunk.web.uri not in seen_urls:
                    seen_urls.add(chunk.web.uri)
                    sources.append({
                        "url": chunk.web.uri,
                        "title": chunk.web.title or chunk.web.uri,
                    })

    return sources[:max_results]


async def extract_seed_title(seed_text: str) -> str:
    """Generate a short title for a notebook from seed text."""
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=f"Generate a short title (5 words max) for a research notebook about this text. Return ONLY the title, nothing else.\n\n{seed_text[:2000]}",
    )
    return response.text.strip().strip('"')
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/trinabgoswamy/Synapse/backend
PYTHONPATH=. pytest tests/test_discovery.py -v
```

Expected: PASS — returns list of URLs with titles from Google Search grounding.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/discovery.py backend/tests/test_discovery.py
git commit -m "feat: implement discovery service using Gemini Search Grounding"
```

---

## Task 5: Crawler Service

**Files:**
- Create: `backend/app/services/crawler.py`
- Create: `backend/tests/test_crawler.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_crawler.py`:
```python
import pytest
from app.services.crawler import crawl_url


@pytest.mark.asyncio
async def test_crawl_extracts_text():
    """Crawling a known URL should return extracted text content."""
    result = await crawl_url("https://en.wikipedia.org/wiki/Neural_network")

    assert result is not None
    assert "text" in result
    assert len(result["text"]) > 100
    assert "title" in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. pytest tests/test_crawler.py -v
```

Expected: FAIL — `crawl_url` does not exist.

- [ ] **Step 3: Implement crawler**

Create `backend/app/services/crawler.py`:
```python
import httpx
import trafilatura


async def crawl_url(url: str, timeout: float = 15.0) -> dict | None:
    """Fetch a URL and extract clean text content.

    Returns {"text": ..., "title": ...} or None on failure.
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Synapse-Bot/1.0 (research tool)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text
    except (httpx.HTTPError, httpx.TimeoutException):
        return None

    text = trafilatura.extract(html, include_comments=False, include_tables=True)
    if not text or len(text) < 50:
        return None

    metadata = trafilatura.extract(html, output_format="json", include_comments=False)
    title = ""
    if metadata:
        import json
        try:
            meta = json.loads(metadata)
            title = meta.get("title", "")
        except json.JSONDecodeError:
            pass

    return {
        "text": text[:15000],  # Cap at ~15k chars to control token usage
        "title": title or url,
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
PYTHONPATH=. pytest tests/test_crawler.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/crawler.py backend/tests/test_crawler.py
git commit -m "feat: implement URL crawler with trafilatura text extraction"
```

---

## Task 6: Document Processor (Summarize + Embed)

**Files:**
- Create: `backend/app/services/processor.py`
- Create: `backend/tests/test_processor.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_processor.py`:
```python
import pytest
from app.services.processor import summarize_document, embed_document


@pytest.mark.asyncio
async def test_summarize_returns_string():
    text = "Neural networks are computational systems inspired by biological neural networks. They consist of layers of interconnected nodes that process information. Deep learning uses multiple layers to progressively extract higher-level features from raw input."
    summary = await summarize_document(text, "Neural Networks Overview")
    assert isinstance(summary, str)
    assert len(summary) > 20
    assert len(summary) < 1000


@pytest.mark.asyncio
async def test_embed_returns_vector():
    text = "Neural networks are computational systems inspired by biological neural networks."
    embedding = await embed_document(text)
    assert isinstance(embedding, list)
    assert len(embedding) == 768  # gemini-embedding-001 output dimension
    assert all(isinstance(x, float) for x in embedding)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. pytest tests/test_processor.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement processor**

Create `backend/app/services/processor.py`:
```python
from google import genai
from app.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_EMBED_MODEL

client = genai.Client(api_key=GEMINI_API_KEY)


async def summarize_document(text: str, title: str) -> str:
    """Generate a 2-3 sentence summary of a document."""
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=f"Summarize this document in 2-3 sentences. Be specific about the key claims and findings.\n\nTitle: {title}\n\n{text[:6000]}",
    )
    return response.text.strip()


async def embed_document(text: str) -> list[float]:
    """Generate an embedding vector for a document's text."""
    # Truncate to fit embedding model's context window
    truncated = text[:8000]
    result = client.models.embed_content(
        model=GEMINI_EMBED_MODEL,
        contents=truncated,
    )
    return [float(x) for x in result.embeddings[0].values]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
PYTHONPATH=. pytest tests/test_processor.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/processor.py backend/tests/test_processor.py
git commit -m "feat: implement document summarization and embedding via Gemini"
```

---

## Task 7: Graph Edge Computation

**Files:**
- Create: `backend/app/services/graph.py`
- Create: `backend/tests/test_graph.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_graph.py`:
```python
import pytest
from app.services.graph import compute_edges


def test_compute_edges_from_embeddings():
    """Given documents with embeddings, compute similarity edges."""
    docs = [
        {"id": "a", "title": "Doc A", "embedding": [1.0, 0.0, 0.0]},
        {"id": "b", "title": "Doc B", "embedding": [0.9, 0.1, 0.0]},  # Similar to A
        {"id": "c", "title": "Doc C", "embedding": [0.0, 0.0, 1.0]},  # Different
    ]
    edges = compute_edges(docs, threshold=0.5)

    assert len(edges) >= 1
    # A and B should be connected (high similarity)
    ab_edge = [e for e in edges if set([e["source_a"], e["source_b"]]) == {"a", "b"}]
    assert len(ab_edge) == 1
    assert ab_edge[0]["similarity"] > 0.5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. pytest tests/test_graph.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement graph edge computation**

Create `backend/app/services/graph.py`:
```python
import numpy as np
from google import genai
from app.config import GEMINI_API_KEY, GEMINI_MODEL

client = genai.Client(api_key=GEMINI_API_KEY)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr = np.array(a)
    b_arr = np.array(b)
    dot = np.dot(a_arr, b_arr)
    norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def compute_edges(docs: list[dict], threshold: float = 0.4) -> list[dict]:
    """Compute pairwise cosine similarity between document embeddings.

    Returns edges where similarity > threshold.
    """
    edges = []
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            sim = cosine_similarity(docs[i]["embedding"], docs[j]["embedding"])
            if sim >= threshold:
                edges.append({
                    "source_a": docs[i]["id"],
                    "source_b": docs[j]["id"],
                    "similarity": round(sim, 4),
                })
    return edges


async def generate_edge_labels(edges: list[dict], docs_by_id: dict[str, dict]) -> list[dict]:
    """Use Gemini to generate human-readable relationship labels for edges.

    docs_by_id: {source_id: {"title": ..., "summary": ...}}
    """
    if not edges:
        return edges

    # Batch: describe relationships for up to 20 edges at once
    edge_descriptions = []
    for edge in edges[:20]:
        a = docs_by_id.get(edge["source_a"], {})
        b = docs_by_id.get(edge["source_b"], {})
        edge_descriptions.append(
            f"- \"{a.get('title', '?')}\" (summary: {a.get('summary', 'N/A')[:200]}) ↔ \"{b.get('title', '?')}\" (summary: {b.get('summary', 'N/A')[:200]})"
        )

    prompt = f"""For each pair of documents below, write a short phrase (under 10 words) explaining how they are related. Return one line per pair, in the same order. No numbering, no bullets.

{chr(10).join(edge_descriptions)}"""

    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    labels = response.text.strip().split("\n")

    for i, edge in enumerate(edges[:20]):
        if i < len(labels):
            edge["relationship"] = labels[i].strip()

    return edges
```

- [ ] **Step 4: Run test to verify it passes**

```bash
PYTHONPATH=. pytest tests/test_graph.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/graph.py backend/tests/test_graph.py
git commit -m "feat: implement document similarity edge computation"
```

---

## Task 8: Orchestration Pipeline (Celery Worker)

**Files:**
- Create: `backend/app/worker.py`

This ties discovery → crawl → process → graph into a single async pipeline triggered when a notebook is created.

- [ ] **Step 1: Implement the worker**

Create `backend/app/worker.py`:
```python
import asyncio
from celery import Celery
from app.config import REDIS_URL

celery_app = Celery("synapse", broker=REDIS_URL, backend=REDIS_URL)


def run_async(coro):
    """Helper to run async functions from sync Celery tasks."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="process_notebook")
def process_notebook(notebook_id: str, seed_text: str):
    """Full pipeline: discover → crawl → summarize → embed → compute graph."""
    from app.database import (
        create_source, update_source, update_notebook_status,
        get_sources, create_edge, get_sources_with_embeddings,
    )
    from app.services.discovery import discover_related_sources
    from app.services.crawler import crawl_url
    from app.services.processor import summarize_document, embed_document
    from app.services.graph import compute_edges, generate_edge_labels

    try:
        # 1. Create seed as the first source
        seed_source = run_async(create_source(
            notebook_id=notebook_id,
            url=None,
            title="Seed Document",
            source_type="seed",
        ))
        run_async(update_source(
            seed_source["id"],
            content=seed_text,
            status="processing",
        ))

        # Summarize and embed the seed
        seed_summary = run_async(summarize_document(seed_text, "Seed Document"))
        seed_embedding = run_async(embed_document(seed_text))
        run_async(update_source(
            seed_source["id"],
            summary=seed_summary,
            embedding=seed_embedding,
            status="ready",
        ))

        # 2. Discover related sources
        discovered = run_async(discover_related_sources(seed_text, max_results=15))

        # 3. Create source records for all discovered URLs
        source_records = []
        for item in discovered:
            record = run_async(create_source(
                notebook_id=notebook_id,
                url=item["url"],
                title=item["title"],
                source_type="webpage",
            ))
            source_records.append(record)

        # 4. Crawl, summarize, and embed each source
        for record in source_records:
            run_async(update_source(record["id"], status="crawling"))
            crawled = run_async(crawl_url(record["url"]))

            if not crawled:
                run_async(update_source(record["id"], status="error", error_message="Failed to fetch"))
                continue

            run_async(update_source(
                record["id"],
                content=crawled["text"],
                title=crawled["title"] or record["title"],
                status="processing",
            ))

            summary = run_async(summarize_document(crawled["text"], crawled["title"]))
            embedding = run_async(embed_document(crawled["text"]))

            run_async(update_source(
                record["id"],
                summary=summary,
                embedding=embedding,
                status="ready",
            ))

        # 5. Compute graph edges
        all_docs = run_async(get_sources_with_embeddings(notebook_id))
        docs_for_graph = [d for d in all_docs if d.get("embedding")]
        edges = compute_edges(docs_for_graph, threshold=0.4)

        # 6. Generate edge labels
        sources_list = run_async(get_sources(notebook_id))
        docs_by_id = {s["id"]: s for s in sources_list}
        edges = run_async(generate_edge_labels(edges, docs_by_id))

        # 7. Save edges to DB
        for edge in edges:
            run_async(create_edge(
                notebook_id=notebook_id,
                source_a=edge["source_a"],
                source_b=edge["source_b"],
                similarity=edge["similarity"],
                relationship=edge.get("relationship"),
            ))

        # 8. Mark notebook as ready
        run_async(update_notebook_status(notebook_id, "ready"))

    except Exception as e:
        run_async(update_notebook_status(notebook_id, "error"))
        raise e
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/worker.py
git commit -m "feat: implement Celery worker for notebook processing pipeline"
```

---

## Task 9: API Routes

**Files:**
- Create: `backend/app/routers/notebooks.py`
- Create: `backend/app/routers/sources.py`
- Create: `backend/app/routers/chat.py`
- Create: `backend/app/services/rag.py`
- Modify: `backend/app/main.py` (register routers)

- [ ] **Step 1: Implement notebooks router**

Create `backend/app/routers/notebooks.py`:
```python
from fastapi import APIRouter, HTTPException
from app.models import CreateNotebookRequest, NotebookResponse, SourceResponse, EdgeResponse
from app.database import create_notebook, get_notebook, get_sources, get_edges
from app.services.discovery import extract_seed_title
from app.services.crawler import crawl_url
from app.worker import process_notebook

router = APIRouter(prefix="/api/notebooks", tags=["notebooks"])


@router.post("", response_model=dict)
async def create_notebook_endpoint(req: CreateNotebookRequest):
    """Create a new notebook from a seed URL or text."""
    seed_text = req.seed_text

    # If URL provided, crawl it first to get text
    if req.seed_url:
        crawled = await crawl_url(req.seed_url)
        if not crawled:
            raise HTTPException(status_code=400, detail="Could not fetch the provided URL")
        seed_text = crawled["text"]
        title = req.title or crawled["title"]
    else:
        if not seed_text:
            raise HTTPException(status_code=400, detail="Provide seed_url or seed_text")
        title = req.title or await extract_seed_title(seed_text)

    notebook = await create_notebook(title=title, seed_url=req.seed_url, seed_text=seed_text)

    # Kick off async processing pipeline
    process_notebook.delay(notebook["id"], seed_text)

    return {"id": notebook["id"], "title": notebook["title"], "status": "discovering"}


@router.get("/{notebook_id}", response_model=NotebookResponse)
async def get_notebook_endpoint(notebook_id: str):
    """Get notebook with all sources and edges."""
    notebook = await get_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    sources = await get_sources(notebook_id)
    edges = await get_edges(notebook_id)

    return NotebookResponse(
        id=notebook["id"],
        title=notebook["title"],
        status=notebook["status"],
        sources=[SourceResponse(**s) for s in sources],
        edges=[EdgeResponse(**e) for e in edges],
    )
```

- [ ] **Step 2: Implement RAG service**

Create `backend/app/services/rag.py`:
```python
from google import genai
from app.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_EMBED_MODEL
from app.services.graph import cosine_similarity

client = genai.Client(api_key=GEMINI_API_KEY)


async def retrieve_relevant_sources(query: str, sources: list[dict], top_k: int = 5) -> list[dict]:
    """Embed the query and find most similar sources."""
    query_result = client.models.embed_content(
        model=GEMINI_EMBED_MODEL,
        contents=query,
    )
    query_embedding = [float(x) for x in query_result.embeddings[0].values]

    scored = []
    for source in sources:
        if not source.get("embedding"):
            continue
        sim = cosine_similarity(query_embedding, source["embedding"])
        scored.append({**source, "_score": sim})

    scored.sort(key=lambda x: x["_score"], reverse=True)
    return scored[:top_k]


async def generate_answer(query: str, relevant_sources: list[dict], chat_history: list[dict]) -> dict:
    """Generate a grounded answer using retrieved sources."""
    context_parts = []
    cited_ids = []
    for s in relevant_sources:
        content_preview = (s.get("content") or s.get("summary") or "")[:3000]
        context_parts.append(f"[Source: {s['title']}]\n{content_preview}")
        cited_ids.append(s["id"])

    context = "\n\n---\n\n".join(context_parts)

    history_text = ""
    if chat_history:
        recent = chat_history[-6:]  # Last 3 exchanges
        history_text = "\n".join(f"{m['role']}: {m['content']}" for m in recent)
        history_text = f"\nRecent conversation:\n{history_text}\n"

    prompt = f"""You are a research assistant. Answer the user's question based ONLY on the provided sources. Cite which source you're drawing from. If the sources don't contain the answer, say so.
{history_text}
Sources:
{context}

User question: {query}"""

    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)

    return {
        "content": response.text,
        "sources_cited": cited_ids,
    }
```

- [ ] **Step 3: Implement chat router**

Create `backend/app/routers/chat.py`:
```python
from fastapi import APIRouter, HTTPException
from app.models import ChatRequest, ChatMessage
from app.database import get_sources, get_messages, add_message
from app.services.rag import retrieve_relevant_sources, generate_answer

router = APIRouter(prefix="/api/notebooks/{notebook_id}/chat", tags=["chat"])


@router.get("", response_model=list[ChatMessage])
async def get_chat_history(notebook_id: str):
    messages = await get_messages(notebook_id)
    return [ChatMessage(**m) for m in messages]


@router.post("", response_model=ChatMessage)
async def send_message(notebook_id: str, req: ChatRequest):
    # Save user message
    await add_message(notebook_id, "user", req.message)

    # Get all sources with embeddings
    sources = await get_sources(notebook_id)
    ready_sources = [s for s in sources if s.get("status") == "ready"]

    if not ready_sources:
        raise HTTPException(status_code=400, detail="No sources ready yet. Please wait for processing to complete.")

    # Retrieve relevant sources
    relevant = await retrieve_relevant_sources(req.message, ready_sources, top_k=5)

    # Get chat history for context
    history = await get_messages(notebook_id)

    # Generate answer
    answer = await generate_answer(req.message, relevant, history)

    # Save assistant message
    msg = await add_message(notebook_id, "assistant", answer["content"], answer["sources_cited"])
    return ChatMessage(**msg)
```

- [ ] **Step 4: Implement sources router**

Create `backend/app/routers/sources.py`:
```python
from fastapi import APIRouter
from app.models import SourceResponse
from app.database import get_sources

router = APIRouter(prefix="/api/notebooks/{notebook_id}/sources", tags=["sources"])


@router.get("", response_model=list[SourceResponse])
async def list_sources(notebook_id: str):
    sources = await get_sources(notebook_id)
    return [SourceResponse(**s) for s in sources]
```

- [ ] **Step 5: Register routers in main.py**

Replace `backend/app/main.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import notebooks, sources, chat

app = FastAPI(title="Synapse API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(notebooks.router)
app.include_router(sources.router)
app.include_router(chat.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/ backend/app/services/rag.py backend/app/main.py
git commit -m "feat: implement API routes for notebooks, sources, and chat"
```

---

## Task 10: Frontend API Client

**Files:**
- Create: `frontend/src/api.js`

- [ ] **Step 1: Implement API client**

Create `frontend/src/api.js`:
```javascript
const BASE = '/api';

export async function createNotebook({ seedUrl, seedText, title }) {
  const res = await fetch(`${BASE}/notebooks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      seed_url: seedUrl || undefined,
      seed_text: seedText || undefined,
      title: title || undefined,
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getNotebook(id) {
  const res = await fetch(`${BASE}/notebooks/${id}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getSources(notebookId) {
  const res = await fetch(`${BASE}/notebooks/${notebookId}/sources`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function sendChatMessage(notebookId, message) {
  const res = await fetch(`${BASE}/notebooks/${notebookId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getChatHistory(notebookId) {
  const res = await fetch(`${BASE}/notebooks/${notebookId}/chat`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api.js
git commit -m "feat: add frontend API client"
```

---

## Task 11: Frontend - Seed Input Modal

**Files:**
- Create: `frontend/src/components/SeedInput.jsx`

- [ ] **Step 1: Implement seed input component**

Create `frontend/src/components/SeedInput.jsx`:
```jsx
import React, { useState } from 'react';
import { Upload, Link, FileText, ArrowRight, Loader2 } from 'lucide-react';

export default function SeedInput({ onSubmit, isLoading }) {
  const [mode, setMode] = useState('url'); // 'url' or 'text'
  const [seedUrl, setSeedUrl] = useState('');
  const [seedText, setSeedText] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (mode === 'url' && seedUrl.trim()) {
      onSubmit({ seedUrl: seedUrl.trim() });
    } else if (mode === 'text' && seedText.trim()) {
      onSubmit({ seedText: seedText.trim() });
    }
  };

  const canSubmit = mode === 'url' ? seedUrl.trim() : seedText.trim();

  return (
    <div className="h-screen w-screen bg-[#f0f4f9] flex items-center justify-center">
      <div className="w-full max-w-xl mx-4">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-normal text-[#1f1f1f] tracking-tight mb-2">
            Synapse Notebook
          </h1>
          <p className="text-[#444746] text-base">
            Paste a URL or text to build your knowledge base
          </p>
        </div>

        <div className="bg-white rounded-3xl p-8 shadow-sm border border-[#e0e2e0]">
          {/* Mode Toggle */}
          <div className="flex gap-2 mb-6">
            <button
              onClick={() => setMode('url')}
              className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                mode === 'url'
                  ? 'bg-[#0b57d0] text-white'
                  : 'bg-[#f0f4f9] text-[#444746] hover:bg-[#e1e3e1]'
              }`}
            >
              <Link className="w-4 h-4" /> URL
            </button>
            <button
              onClick={() => setMode('text')}
              className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                mode === 'text'
                  ? 'bg-[#0b57d0] text-white'
                  : 'bg-[#f0f4f9] text-[#444746] hover:bg-[#e1e3e1]'
              }`}
            >
              <FileText className="w-4 h-4" /> Text
            </button>
          </div>

          <form onSubmit={handleSubmit}>
            {mode === 'url' ? (
              <input
                type="url"
                value={seedUrl}
                onChange={(e) => setSeedUrl(e.target.value)}
                placeholder="https://example.com/article..."
                className="w-full bg-[#f0f4f9] rounded-2xl px-5 py-4 text-[15px] focus:outline-none focus:ring-2 focus:ring-[#0b57d0] text-[#1f1f1f] placeholder:text-[#444746] mb-4"
                autoFocus
              />
            ) : (
              <textarea
                value={seedText}
                onChange={(e) => setSeedText(e.target.value)}
                placeholder="Paste article text, research notes, or any content..."
                rows={6}
                className="w-full bg-[#f0f4f9] rounded-2xl px-5 py-4 text-[15px] focus:outline-none focus:ring-2 focus:ring-[#0b57d0] text-[#1f1f1f] placeholder:text-[#444746] mb-4 resize-none"
                autoFocus
              />
            )}

            <button
              type="submit"
              disabled={!canSubmit || isLoading}
              className="w-full bg-[#0b57d0] hover:bg-[#0842a0] disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium text-sm py-3.5 rounded-full transition-colors flex items-center justify-center gap-2"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Discovering sources...
                </>
              ) : (
                <>
                  Build Knowledge Base <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/SeedInput.jsx
git commit -m "feat: add seed input modal component"
```

---

## Task 12: Frontend - Split App.jsx into Components

**Files:**
- Create: `frontend/src/components/Header.jsx`
- Create: `frontend/src/components/SourcesPanel.jsx`
- Create: `frontend/src/components/DocumentWeb.jsx`
- Create: `frontend/src/components/NodePopover.jsx`
- Create: `frontend/src/components/ChatPanel.jsx`
- Create: `frontend/src/hooks/useNotebook.js`
- Create: `frontend/src/hooks/useChat.js`
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Create useNotebook hook**

Create `frontend/src/hooks/useNotebook.js`:
```javascript
import { useState, useEffect, useRef } from 'react';
import { getNotebook } from '../api';

export default function useNotebook(notebookId) {
  const [notebook, setNotebook] = useState(null);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef(null);

  useEffect(() => {
    if (!notebookId) return;

    const fetchNotebook = async () => {
      try {
        const data = await getNotebook(notebookId);
        setNotebook(data);
        setLoading(false);

        // Stop polling once notebook is ready or errored
        if (data.status === 'ready' || data.status === 'error') {
          if (intervalRef.current) clearInterval(intervalRef.current);
        }
      } catch (err) {
        console.error('Failed to fetch notebook:', err);
        setLoading(false);
      }
    };

    fetchNotebook();
    // Poll every 3 seconds while discovering
    intervalRef.current = setInterval(fetchNotebook, 3000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [notebookId]);

  return { notebook, loading };
}
```

- [ ] **Step 2: Create useChat hook**

Create `frontend/src/hooks/useChat.js`:
```javascript
import { useState, useEffect } from 'react';
import { getChatHistory, sendChatMessage } from '../api';

export default function useChat(notebookId) {
  const [messages, setMessages] = useState([]);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!notebookId) return;
    getChatHistory(notebookId).then(setMessages).catch(console.error);
  }, [notebookId]);

  const send = async (text) => {
    if (!text.trim() || sending) return;

    // Optimistic UI: add user message immediately
    const userMsg = { role: 'user', content: text, sources_cited: [] };
    setMessages((prev) => [...prev, userMsg]);
    setSending(true);

    try {
      const response = await sendChatMessage(notebookId, text);
      setMessages((prev) => [...prev, response]);
    } catch (err) {
      console.error('Chat error:', err);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Something went wrong. Please try again.', sources_cited: [] },
      ]);
    } finally {
      setSending(false);
    }
  };

  return { messages, send, sending };
}
```

- [ ] **Step 3: Create Header component**

Create `frontend/src/components/Header.jsx`:
```jsx
import React from 'react';
import { BookOpen, HelpCircle, Bell } from 'lucide-react';

export default function Header({ title }) {
  return (
    <header className="flex items-center justify-between px-6 py-4 z-10">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
          <BookOpen className="w-5 h-5 text-[#0b57d0]" />
        </div>
        <h1 className="font-normal text-xl tracking-tight text-[#1f1f1f]">
          {title || 'Synapse Notebook'}
        </h1>
      </div>
      <div className="flex items-center gap-4 text-[#444746]">
        <button className="w-10 h-10 rounded-full hover:bg-black/5 flex items-center justify-center transition-colors">
          <HelpCircle className="w-5 h-5" />
        </button>
        <button className="w-10 h-10 rounded-full hover:bg-black/5 flex items-center justify-center transition-colors relative">
          <Bell className="w-5 h-5" />
        </button>
        <button className="w-8 h-8 rounded-full bg-[#0b57d0] text-white flex items-center justify-center font-medium text-sm ml-2">
          U
        </button>
      </div>
    </header>
  );
}
```

- [ ] **Step 4: Create SourcesPanel component**

Create `frontend/src/components/SourcesPanel.jsx`:
```jsx
import React from 'react';
import { FileText, Globe, Upload, Plus, ExternalLink } from 'lucide-react';

export default function SourcesPanel({ sources, onSourceClick }) {
  return (
    <section className="w-80 flex flex-col gap-4 overflow-y-auto pr-1 pb-4 no-scrollbar">
      <div className="flex items-center justify-between px-2">
        <h2 className="text-sm font-medium text-[#1f1f1f]">
          Sources {sources.length > 0 && <span className="text-[#444746]">({sources.length})</span>}
        </h2>
      </div>

      <div className="flex flex-col gap-2">
        {sources.map((source) => (
          <SourceCard key={source.id} source={source} onClick={() => onSourceClick(source)} />
        ))}
        {sources.length === 0 && (
          <p className="text-sm text-[#444746] px-4 py-8 text-center">
            Discovering sources...
          </p>
        )}
      </div>
    </section>
  );
}

function SourceCard({ source, onClick }) {
  const statusColors = {
    pending: 'bg-[#e0e2e0]',
    crawling: 'bg-[#fbbc04] animate-pulse',
    processing: 'bg-[#fbbc04] animate-pulse',
    ready: 'bg-[#34a853]',
    error: 'bg-[#ea4335]',
  };

  const icon = source.source_type === 'seed' ? (
    <Upload className="w-5 h-5 text-[#0b57d0]" />
  ) : source.status === 'error' ? (
    <FileText className="w-5 h-5 text-[#ea4335]" />
  ) : (
    <Globe className="w-5 h-5 text-[#0b57d0]" />
  );

  return (
    <div
      onClick={onClick}
      className="group bg-white rounded-3xl p-4 flex flex-col gap-1 cursor-pointer transition-all border border-transparent hover:bg-black/[0.02]"
    >
      <div className="flex items-start gap-3">
        <div className="mt-1 shrink-0">{icon}</div>
        <div className="flex-1 overflow-hidden">
          <h3 className="text-sm font-medium text-[#1f1f1f] truncate pr-2">{source.title}</h3>
          <p className="text-xs text-[#444746] mt-0.5 flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${statusColors[source.status] || statusColors.pending}`} />
            {source.status === 'ready' && source.summary
              ? source.summary.slice(0, 80) + '...'
              : source.status}
          </p>
          {source.url && source.status === 'ready' && (
            <p className="text-xs text-[#0b57d0] mt-1 truncate">{new URL(source.url).hostname}</p>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create DocumentWeb component (d3-force graph)**

Create `frontend/src/components/DocumentWeb.jsx`:
```jsx
import React, { useRef, useEffect, useState } from 'react';
import * as d3 from 'd3-force';
import { Sparkles, Crosshair, Plus, Minus, RotateCcw } from 'lucide-react';
import NodePopover from './NodePopover';

const SOURCE_COLORS = {
  seed: '#A142F4',
  webpage: '#4285F4',
  pdf: '#EA4335',
};

export default function DocumentWeb({ sources, edges }) {
  const canvasRef = useRef(null);
  const simRef = useRef(null);
  const nodesRef = useRef([]);
  const linksRef = useRef([]);
  const transformRef = useRef({ x: 0, y: 0, k: 1 });
  const dragRef = useRef(null);
  const [selectedNode, setSelectedNode] = useState(null);

  // Build nodes and links from props
  useEffect(() => {
    const readySources = sources.filter((s) => s.status === 'ready');
    if (readySources.length === 0) return;

    const nodes = readySources.map((s) => ({
      id: s.id,
      title: s.title,
      summary: s.summary,
      url: s.url,
      source_type: s.source_type,
      r: s.source_type === 'seed' ? 28 : 16 + Math.min(s.title.length / 3, 10),
    }));

    const nodeIds = new Set(nodes.map((n) => n.id));
    const links = edges
      .filter((e) => nodeIds.has(e.source_a) && nodeIds.has(e.source_b))
      .map((e) => ({
        source: e.source_a,
        target: e.source_b,
        similarity: e.similarity,
        relationship: e.relationship,
      }));

    nodesRef.current = nodes;
    linksRef.current = links;

    const sim = d3.forceSimulation(nodes)
      .force('charge', d3.forceManyBody().strength(-300))
      .force('link', d3.forceLink(links).id((d) => d.id).distance(150))
      .force('center', d3.forceCenter(0, 0))
      .force('collision', d3.forceCollide().radius((d) => d.r + 10))
      .on('tick', draw);

    simRef.current = sim;

    return () => sim.stop();
  }, [sources, edges]);

  const draw = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    const t = transformRef.current;
    const cx = width / 2;
    const cy = height / 2;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#fafafa';
    ctx.fillRect(0, 0, width, height);

    ctx.save();
    ctx.translate(cx + t.x, cy + t.y);
    ctx.scale(t.k, t.k);

    // Draw links
    linksRef.current.forEach((link) => {
      const s = link.source;
      const tgt = link.target;
      if (!s.x || !tgt.x) return;

      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(tgt.x, tgt.y);
      ctx.strokeStyle = `rgba(196, 199, 197, ${0.3 + link.similarity * 0.5})`;
      ctx.lineWidth = 1 + link.similarity * 2;
      ctx.stroke();
    });

    // Draw nodes
    nodesRef.current.forEach((n) => {
      if (!n.x) return;
      const color = SOURCE_COLORS[n.source_type] || SOURCE_COLORS.webpage;

      // Shadow
      ctx.shadowColor = 'rgba(0,0,0,0.12)';
      ctx.shadowBlur = 8;
      ctx.shadowOffsetY = 2;

      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();

      ctx.shadowColor = 'transparent';
      ctx.lineWidth = 2;
      ctx.strokeStyle = '#ffffff';
      ctx.stroke();

      // Label
      ctx.fillStyle = '#1f1f1f';
      ctx.font = '500 11px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      const label = n.title.length > 25 ? n.title.slice(0, 23) + '...' : n.title;
      ctx.lineWidth = 3;
      ctx.strokeStyle = 'rgba(255,255,255,0.9)';
      ctx.strokeText(label, n.x, n.y + n.r + 6);
      ctx.fillText(label, n.x, n.y + n.r + 6);
    });

    ctx.restore();
  };

  // Pan and zoom handlers
  const handleWheel = (e) => {
    e.preventDefault();
    const scale = e.deltaY > 0 ? 0.95 : 1.05;
    transformRef.current.k = Math.max(0.3, Math.min(3, transformRef.current.k * scale));
    draw();
  };

  const handleMouseDown = (e) => {
    dragRef.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseMove = (e) => {
    if (!dragRef.current) return;
    transformRef.current.x += e.clientX - dragRef.current.x;
    transformRef.current.y += e.clientY - dragRef.current.y;
    dragRef.current = { x: e.clientX, y: e.clientY };
    draw();
  };

  const handleMouseUp = () => {
    dragRef.current = null;
  };

  const handleClick = (e) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const t = transformRef.current;
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const mx = (e.clientX - rect.left - cx - t.x) / t.k;
    const my = (e.clientY - rect.top - cy - t.y) / t.k;

    const clicked = nodesRef.current.find((n) => {
      const dx = n.x - mx;
      const dy = n.y - my;
      return dx * dx + dy * dy < n.r * n.r;
    });

    setSelectedNode(clicked || null);
  };

  const resetView = () => {
    transformRef.current = { x: 0, y: 0, k: 1 };
    draw();
  };

  return (
    <section className="flex-1 bg-white rounded-[2rem] relative overflow-hidden flex flex-col shadow-sm border border-[#e0e2e0]">
      <div className="absolute top-6 left-6 z-10 bg-white/80 backdrop-blur-md py-1.5 px-4 rounded-full border border-[#e0e2e0] shadow-sm">
        <h2 className="text-sm font-medium text-[#1f1f1f] flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-[#0b57d0]" />
          Document Web
        </h2>
      </div>

      <canvas
        ref={canvasRef}
        className="flex-1 w-full h-full cursor-grab active:cursor-grabbing outline-none"
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onClick={handleClick}
        style={{ touchAction: 'none' }}
      />

      {selectedNode && (
        <NodePopover node={selectedNode} onClose={() => setSelectedNode(null)} />
      )}

      <div className="absolute bottom-6 right-6 flex bg-white rounded-full overflow-hidden shadow-sm border border-[#e0e2e0] p-1">
        <button onClick={resetView} className="w-10 h-10 flex items-center justify-center text-[#444746] hover:bg-[#f0f4f9] rounded-full transition-all">
          <Crosshair size={18} />
        </button>
        <button onClick={() => { transformRef.current.k = Math.min(3, transformRef.current.k * 1.2); draw(); }} className="w-10 h-10 flex items-center justify-center text-[#444746] hover:bg-[#f0f4f9] rounded-full transition-all">
          <Plus size={18} />
        </button>
        <button onClick={() => { transformRef.current.k = Math.max(0.3, transformRef.current.k * 0.8); draw(); }} className="w-10 h-10 flex items-center justify-center text-[#444746] hover:bg-[#f0f4f9] rounded-full transition-all">
          <Minus size={18} />
        </button>
        <button onClick={() => { if (simRef.current) simRef.current.alpha(0.5).restart(); }} className="w-10 h-10 flex items-center justify-center text-[#444746] hover:bg-[#f0f4f9] rounded-full transition-all">
          <RotateCcw size={18} />
        </button>
      </div>
    </section>
  );
}
```

- [ ] **Step 6: Create NodePopover component**

Create `frontend/src/components/NodePopover.jsx`:
```jsx
import React from 'react';
import { MoreVertical, ExternalLink, X } from 'lucide-react';

export default function NodePopover({ node, onClose }) {
  return (
    <div className="absolute top-1/2 left-1/2 transform translate-x-12 -translate-y-12 w-[340px] bg-white rounded-3xl p-6 z-20 shadow-[0_8px_30px_rgb(0,0,0,0.08)] border border-[#e0e2e0]">
      <div className="flex items-start justify-between mb-2">
        <h3 className="text-base font-medium text-[#1f1f1f] pr-4">{node.title}</h3>
        <button onClick={onClose} className="w-8 h-8 rounded-full hover:bg-black/5 flex items-center justify-center -mr-2 -mt-2">
          <X className="w-5 h-5 text-[#444746]" />
        </button>
      </div>

      <div className="space-y-3 text-sm text-[#444746] mb-6">
        <p className="flex gap-2">
          <span className="font-medium text-[#1f1f1f] w-16">Type:</span>
          <span className="bg-[#f0f4f9] px-2 py-0.5 rounded-md text-xs font-medium text-[#0b57d0]">
            {node.source_type}
          </span>
        </p>
        {node.url && (
          <p className="flex gap-2">
            <span className="font-medium text-[#1f1f1f] w-16">URL:</span>
            <span className="truncate text-[#0b57d0]">{new URL(node.url).hostname}</span>
          </p>
        )}
        {node.summary && (
          <div className="pt-3 border-t border-[#f0f4f9]">
            <p className="leading-relaxed">{node.summary}</p>
          </div>
        )}
      </div>

      <div className="flex gap-3">
        {node.url && (
          <a
            href={node.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 text-[#0b57d0] hover:bg-blue-50 font-medium text-sm py-2 rounded-full transition-colors border border-[#c2e7ff] flex items-center justify-center gap-1"
          >
            <ExternalLink className="w-3.5 h-3.5" /> Open Source
          </a>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Create ChatPanel component**

Create `frontend/src/components/ChatPanel.jsx`:
```jsx
import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, FileText, MessageSquare } from 'lucide-react';

export default function ChatPanel({ messages, onSend, sending, sources }) {
  const [input, setInput] = useState('');
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || sending) return;
    onSend(input.trim());
    setInput('');
  };

  const sourcesById = Object.fromEntries((sources || []).map((s) => [s.id, s]));

  return (
    <section className="w-[380px] flex flex-col bg-white rounded-[2rem] overflow-hidden shadow-sm border border-[#e0e2e0] relative">
      <div className="flex items-center px-6 py-5 border-b border-[#f0f4f9] z-10">
        <h2 className="text-base font-medium text-[#1f1f1f] flex items-center gap-2">
          <MessageSquare className="w-5 h-5 text-[#0b57d0]" />
          Notebook Guide
        </h2>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 flex flex-col gap-6 no-scrollbar bg-white">
        {messages.length === 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            <button
              onClick={() => onSend('Summarize all sources')}
              className="bg-[#f0f4f9] hover:bg-[#e1e3e1] cursor-pointer text-[#1f1f1f] text-xs font-medium px-4 py-2 rounded-full border border-transparent transition-colors"
            >
              Summarize sources
            </button>
            <button
              onClick={() => onSend('What are the key themes across these sources?')}
              className="bg-[#f0f4f9] hover:bg-[#e1e3e1] cursor-pointer text-[#1f1f1f] text-xs font-medium px-4 py-2 rounded-full border border-transparent transition-colors"
            >
              Key themes
            </button>
          </div>
        )}

        {messages.map((msg, i) =>
          msg.role === 'user' ? (
            <div key={i} className="flex justify-end">
              <div className="bg-[#f0f4f9] text-[#1f1f1f] text-[15px] py-3 px-5 rounded-3xl rounded-tr-md max-w-[85%]">
                {msg.content}
              </div>
            </div>
          ) : (
            <div key={i} className="flex gap-4">
              <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center shrink-0">
                <Sparkles className="w-4 h-4 text-[#0b57d0]" />
              </div>
              <div className="text-[#1f1f1f] text-[15px] pt-1">
                <p className="whitespace-pre-wrap">{msg.content}</p>
                {msg.sources_cited && msg.sources_cited.length > 0 && (
                  <div className="bg-[#f8f9fa] rounded-2xl p-3 mt-3 border border-[#e0e2e0]">
                    <p className="text-xs text-[#444746] flex items-center gap-2 flex-wrap">
                      <FileText className="w-3.5 h-3.5" />
                      {msg.sources_cited.map((id) => (
                        <span key={id} className="font-medium text-[#0b57d0]">
                          {sourcesById[id]?.title || 'Source'}
                        </span>
                      ))}
                    </p>
                  </div>
                )}
              </div>
            </div>
          )
        )}

        {sending && (
          <div className="flex gap-4">
            <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center shrink-0">
              <Sparkles className="w-4 h-4 text-[#0b57d0] animate-pulse" />
            </div>
            <div className="text-[#444746] text-[15px] pt-2">Thinking...</div>
          </div>
        )}
      </div>

      <div className="p-4 bg-white border-t border-[#f0f4f9]">
        <form onSubmit={handleSubmit} className="relative flex items-center bg-[#f0f4f9] rounded-full px-2 py-1 focus-within:bg-white focus-within:shadow-[0_0_0_1px_#0b57d0] transition-all">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your sources..."
            className="w-full bg-transparent pl-4 pr-12 py-3 text-[15px] focus:outline-none text-[#1f1f1f] placeholder:text-[#444746]"
          />
          <button
            type="submit"
            disabled={!input.trim() || sending}
            className="absolute right-2 w-10 h-10 flex items-center justify-center text-white bg-[#0b57d0] hover:bg-[#0842a0] rounded-full transition-colors disabled:opacity-50"
          >
            <Send className="w-4 h-4 ml-0.5" />
          </button>
        </form>
      </div>
    </section>
  );
}
```

- [ ] **Step 8: Rewrite App.jsx to wire everything together**

Replace `frontend/src/App.jsx`:
```jsx
import React, { useState } from 'react';
import Header from './components/Header';
import SeedInput from './components/SeedInput';
import SourcesPanel from './components/SourcesPanel';
import DocumentWeb from './components/DocumentWeb';
import ChatPanel from './components/ChatPanel';
import useNotebook from './hooks/useNotebook';
import useChat from './hooks/useChat';
import { createNotebook } from './api';

export default function App() {
  const [notebookId, setNotebookId] = useState(null);
  const [creating, setCreating] = useState(false);
  const { notebook, loading } = useNotebook(notebookId);
  const { messages, send, sending } = useChat(notebookId);

  const handleSeed = async (seed) => {
    setCreating(true);
    try {
      const result = await createNotebook(seed);
      setNotebookId(result.id);
    } catch (err) {
      console.error('Failed to create notebook:', err);
    } finally {
      setCreating(false);
    }
  };

  // Show seed input if no notebook yet
  if (!notebookId) {
    return <SeedInput onSubmit={handleSeed} isLoading={creating} />;
  }

  const sources = notebook?.sources || [];
  const edges = notebook?.edges || [];

  return (
    <div className="h-screen w-screen bg-[#f0f4f9] text-[#1f1f1f] font-sans flex flex-col overflow-hidden">
      <Header title={notebook?.title} />
      <main className="flex-1 flex gap-4 px-4 pb-4 overflow-hidden z-10">
        <SourcesPanel sources={sources} onSourceClick={() => {}} />
        <DocumentWeb sources={sources} edges={edges} />
        <ChatPanel messages={messages} onSend={send} sending={sending} sources={sources} />
      </main>

      <style dangerouslySetInnerHTML={{__html: `
        .no-scrollbar::-webkit-scrollbar { display: none; }
        .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
      `}} />
    </div>
  );
}
```

- [ ] **Step 9: Commit**

```bash
git add frontend/src/
git commit -m "feat: split App into components, wire up real data flow"
```

---

## Task 13: End-to-End Smoke Test

**Files:** None new — this is a manual verification task.

- [ ] **Step 1: Start all services**

Terminal 1 — Redis:
```bash
redis-server
```

Terminal 2 — Celery worker:
```bash
cd /Users/trinabgoswamy/Synapse/backend
PYTHONPATH=. celery -A app.worker.celery_app worker --loglevel=info
```

Terminal 3 — FastAPI:
```bash
cd /Users/trinabgoswamy/Synapse/backend
PYTHONPATH=. uvicorn app.main:app --reload --port 8000
```

Terminal 4 — Frontend:
```bash
cd /Users/trinabgoswamy/Synapse/frontend
npm run dev
```

- [ ] **Step 2: Test the full flow**

1. Open http://localhost:5173
2. Paste a URL (e.g., a Wikipedia article or blog post)
3. Click "Build Knowledge Base"
4. Verify: redirects to notebook view, sources panel shows discovered sources populating
5. Wait for sources to reach "ready" status
6. Verify: document web graph renders with nodes and edges
7. Click a node → popover shows summary and source link
8. Type a question in the chat → receive an answer with source citations

- [ ] **Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: end-to-end smoke test fixes"
```

---

## Revised Cost Estimate (Gemini)

Per notebook (1 seed → ~15 discovered sources):

| Operation | Gemini Model | Cost |
|---|---|---|
| Seed topic extraction | 2.5 Flash ($0.30/1M in) | ~$0.001 |
| Discovery (Search Grounding) | 2.5 Flash + Search | ~$0.014 (1 search query) |
| Summarize 15 docs | 2.5 Flash | ~$0.015 |
| Embed 15 docs | embedding-001 ($0.15/1M) | ~$0.001 |
| Edge labels (batch) | 2.5 Flash | ~$0.003 |
| **Per notebook creation** | | **~$0.03** |
| Chat (20 messages) | 2.5 Flash | ~$0.05 |
| **Per active session** | | **~$0.08** |

That's **~5x cheaper than OpenAI** for the same flow.

| Scale | Monthly cost (infra + AI) |
|---|---|
| MVP / just you | ~$0-5/mo |
| 100 users | ~$40-80/mo |
| 1,000 users | ~$200-500/mo |
