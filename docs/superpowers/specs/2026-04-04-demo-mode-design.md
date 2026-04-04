# Demo Mode Design
**Date:** 2026-04-04
**Topic:** Mock demo mode for Synapse — full flow without real backend

---

## Overview

Add a `?demo=true` URL parameter that activates a fully frontend-only demo of Synapse. All API calls are intercepted and served from pre-baked mock data. No backend, Redis, Gemini API key, or Firecrawl required. The demo is completely deterministic and cannot fail.

**Demo seed:**
- URL: `https://en.wikipedia.org/wiki/Large_language_model`
- Title: `How Large Language Models Work`

---

## Activation

`isDemoMode()` checks `window.location.search` for the `demo` param:

```js
function isDemoMode() {
  return new URLSearchParams(window.location.search).has('demo')
}
```

On app mount, `App.jsx` checks `isDemoMode()`. If true, it immediately calls `mockApi.createNotebook()` and sets the notebookId in state — skipping `SeedInput` entirely and going straight to `FormationScreen`.

No UI toggle, no visible "Demo Mode" label. The URL param is the only activation mechanism.

---

## Architecture

### Files changed

| File | Change |
|------|--------|
| `frontend/src/mockApi.js` | **New.** All mock state, state machine, and fake API functions |
| `frontend/src/api.js` | **Modified.** `isDemoMode()` check at the top of each exported function; delegates to `mockApi` when true |
| `frontend/src/App.jsx` | **Modified.** Auto-starts demo on mount if `isDemoMode()` |

All other components (`FormationScreen`, `DocumentWeb`, `ChatPanel`, `SourcesPanel`, `NodePopover`, `SourceComposer`) are **unchanged** — they read from the same data shapes `api.js` already returns.

### Data flow

```
?demo=true → App.jsx detects on mount
           → mockApi.createNotebook() → returns demo notebook ID
           → App sets notebookId → renders FormationScreen
           → FormationScreen polls getNotebook() every 3s
           → mockApi state machine advances source statuses on timer
           → FormationScreen computes stages 1–5 naturally
           → notebook.status = "ready" → App transitions to main layout
           → DocumentWeb renders graph, ChatPanel ready for Q&A
```

---

## Mock State Machine (`mockApi.js`)

Module-level mutable state holds the current notebook snapshot. One `setInterval` (100ms tick) advances sources through statuses based on elapsed time since `createNotebook()` was called.

### Timeline

| t= | Event |
|----|-------|
| 0s | Notebook created. Seed source status: `processing` |
| 2s | Seed → `ready`. 11 discovered sources appear as `pending` |
| 5s | Sources 1–5 → `crawling` |
| 8s | Sources 6–11 → `crawling`. Sources 1–3 → `processing` |
| 11s | Sources 1–3 → `ready`. Sources 4–8 → `processing` |
| 14s | Sources 4–8 → `ready`. Sources 9–11 → `processing` |
| 17s | Sources 9–11 → `ready`. Edges injected into notebook. `notebook.status = "ready"` |

Total formation time: ~17 seconds. The existing `FormationScreen` stage tracker progresses through all 5 stages naturally with no modifications.

`createNotebook()` resets state and restarts the timer — safe to call multiple times.

---

## Mock Data

### Sources (12 total)

| # | Title | URL | Type |
|---|-------|-----|------|
| 0 | Large Language Model *(seed)* | wikipedia.org/wiki/Large_language_model | seed |
| 1 | Attention Is All You Need | arxiv.org/abs/1706.03762 | webpage |
| 2 | The Illustrated Transformer | jalammar.github.io/illustrated-transformer | webpage |
| 3 | GPT-4 Technical Report | arxiv.org/abs/2303.08774 | webpage |
| 4 | BERT: Pre-training of Deep Bidirectional Transformers | arxiv.org/abs/1810.04805 | webpage |
| 5 | Introducing Claude | anthropic.com/news/introducing-claude | webpage |
| 6 | ChatGPT: Optimizing LLMs for Dialogue | openai.com/blog/chatgpt | webpage |
| 7 | Gemini: A Family of Highly Capable Multimodal Models | deepmind.google | webpage |
| 8 | What Are Large Language Models? | blogs.nvidia.com | webpage |
| 9 | The Age of AI Has Begun | gatesnotes.com | webpage |
| 10 | How ChatGPT Actually Works | assemblyai.com/blog | webpage |
| 11 | Stanford AI Index Report 2024 | aiindex.stanford.edu | webpage |

Each source has a realistic 2–3 sentence `summary` used in node popovers and chat citations.

### Edges (18 pre-defined)

Representative connections with `relationship` labels and `similarity` scores:

| Source A | Source B | Relationship | Similarity |
|----------|----------|--------------|------------|
| Wikipedia (seed) | Attention Is All You Need | Foundational architecture | 0.91 |
| Wikipedia (seed) | Illustrated Transformer | Visual explainer of core concepts | 0.87 |
| GPT-4 Report | ChatGPT | Same model family | 0.88 |
| BERT | Illustrated Transformer | Explains BERT's architecture | 0.79 |
| Anthropic/Claude | OpenAI/ChatGPT | Competing frontier labs | 0.72 |
| Gemini | GPT-4 Report | Frontier model comparison | 0.75 |
| Stanford AI Index | Gates Notes | Societal impact of AI | 0.68 |
| NVIDIA LLM explainer | Wikipedia (seed) | Introductory overview | 0.83 |
| AssemblyAI explainer | Illustrated Transformer | Technical walkthrough | 0.77 |
| ... | ... | ... | ... |

The remaining 9 edges follow the same pattern, connecting arXiv papers to explainer articles and cross-linking the lab-specific sources (OpenAI, Anthropic, Google). Full 18-edge list defined in `mockApi.js`.

### Chat Q&A Pairs (5 scripted + fallback)

Matching is keyword-based on the incoming message string (lowercased).

| Match keywords | Response cites sources |
|---------------|----------------------|
| `summarize`, `overview`, `about` | 0, 1, 2, 8 |
| `transformer`, `attention` | 1, 2 |
| `train`, `learn`, `how does it work` | 3, 4, 6 |
| `compan`, `who makes`, `openai`, `google`, `anthropic` | 5, 6, 7 |
| `future`, `risk`, `impact`, `society` | 9, 11 |
| *(fallback — any other message)* | 3 random `ready` sources |

- Responses arrive after a 1.2s artificial delay (feels natural, not instant).
- The two quick-action buttons ("Summarize notebook", "Key themes") map to the first two Q&A pairs.
- `getChatHistory()` returns 2 pre-seeded exchanges so the chat panel is never empty on first open.

### Add Source

`mockApi.addSource()` appends a new source with status `pending` and runs it through `pending → crawling → processing → ready` over ~8 seconds, then appends a new edge connecting it to the 2 most thematically similar existing sources. The graph updates on the next `getNotebook()` poll.

---

## api.js Integration Pattern

`isDemoMode()` is defined once in `api.js` and exported so `App.jsx` can import it from one place:

```js
import * as mockApi from './mockApi.js'

export function isDemoMode() {
  return new URLSearchParams(window.location.search).has('demo')
}

export async function createNotebook(data) {
  if (isDemoMode()) return mockApi.createNotebook(data)
  // existing fetch logic...
}

export async function getNotebook(id) {
  if (isDemoMode()) return mockApi.getNotebook(id)
  // existing fetch logic...
}

// ...same pattern for all other exported functions
```

---

## App.jsx Integration

`App.jsx` imports `isDemoMode` and `createNotebook` from `api.js` — no direct `mockApi` import needed:

```js
import { isDemoMode, createNotebook } from './api.js'

const DEMO_SEED_URL = 'https://en.wikipedia.org/wiki/Large_language_model'
const DEMO_TITLE = 'How Large Language Models Work'

useEffect(() => {
  if (isDemoMode() && !notebookId) {
    createNotebook({ seed_url: DEMO_SEED_URL, title: DEMO_TITLE })
      .then(nb => setNotebookId(nb.id))
  }
}, [])
```

This fires once on mount. If `notebookId` is already set (e.g., from sessionStorage), it does nothing — existing resume logic is unaffected.

---

## What is NOT changed

- `FormationScreen.jsx` — reads source statuses, computes stages identically
- `DocumentWeb.jsx` — renders edges/nodes from the same shapes
- `ChatPanel.jsx` — sends messages and renders responses identically
- `SourcesPanel.jsx` — lists sources identically
- `NodePopover.jsx` — reads `source.summary` identically
- `SourceComposer.jsx` — calls `addSource()` identically
- `Header.jsx` — unchanged
- All backend code — untouched

---

## Non-Goals

- No "Demo Mode" banner or indicator in the UI
- No demo-specific styling or animations
- No backend changes
- Chat responses are not generative (pre-scripted is intentional for reliability)
