# Synapse — Devpost submission

Project narrative for the [Synapse](https://github.com/Hostileoracle0606/Synapse) hackathon submission.
For the technical README, see [`README.md`](README.md).

---

## Inspiration

Most "AI research assistants" today flatten the work into a chat thread. You ask a question, get an answer, lose the trail. The answer might be grounded — but the *connections between sources* aren't.

Real research doesn't look like that. It looks like a network of papers cross-referencing each other, lectures explaining the papers, blog posts critiquing both. We wanted a tool where the **graph of how ideas connect** is the primary surface, with chat as a way to navigate it — not the other way around.

## What it does

Synapse turns a single URL into a navigable knowledge graph in under a minute.

You paste an article, paper, or video link. Synapse:

1. **Reads the seed** with the right parser for its type (trafilatura for HTML, Gemini for PDFs, YouTube captions API for videos)
2. **Discovers ~12 related sources** via three parallel grounded Gemini calls (articles, papers, videos) — guaranteeing a mix of source types instead of mostly webpages
3. **Crawls and summarizes each one in parallel** with a 40-second global deadline
4. **Builds a graph** where edges are weighted keyword overlap on titles + summaries
5. **Lets you chat with the entire corpus** — answers cite sources as `[Source N]`, and those references light up as halos on the corresponding graph nodes

The result: a notebook where the *shape of related material* is visible at a glance, and every answer is anchored to specific sources you can inspect.

## How we built it

**Frontend** is React 19 + Vite + Tailwind 4. The graph is rendered as SVG with d3-force handling layout. We use react-markdown for chat output (with custom components for citation pills) and lucide-react for icons. Tooling and styling were intentionally kept inside the design system rather than reaching for `@tailwindcss/typography` — every UI element is hand-styled to match the rest of the app.

**Backend** is FastAPI on Python 3.13. The notebook pipeline is built around `asyncio.gather`, `asyncio.wait` with timeouts, and bounded semaphores for the parallelism story. There's no separate worker process — `enqueue_notebook_processing` is a single `asyncio.create_task` call that spawns the pipeline as a background task while the HTTP response returns immediately.

**AI layer** is Gemini 2.5 Flash, used for four distinct purposes:

- Three parallel grounded discovery calls (articles, papers, videos) using the `google_search` tool
- Native PDF parsing via `inline_data` (no separate parser library)
- Tools-based ingest (`url_context` + `google_search`) for Twitter, Reddit, LinkedIn — sites that bot-block direct fetches
- Long-context chat: the full notebook corpus is packed into the prompt, with `url_context` available so the model can re-read sources at query time if needed

**Hosting** is Cloudflare Workers for the frontend (static-assets model) and Fly.io for the backend (Dockerfile + auto-stop microVM). The split was deliberate: Cloudflare excels at static, Python on Workers is too restrictive for our pipeline.

## Challenges we ran into

**The frozen-citations bug.** For weeks, citations on the graph would "stick" to whatever the first chat question returned. Subsequent questions seemingly didn't update the highlight. The root cause was a regex (`\[Source\s+(\d+)\]`) that only matched the simplest bracket form `[Source 1]` — Gemini's actual output uses `[Source 1, 2, 3]` or `[Source 1, Source 3]`, which the regex returned 0 matches for. A fallback then attributed the citation to the *first 3 sources unconditionally*, which looked identical between questions. Two interlocking bugs that masked each other; the fix was a more permissive bracket-aware parser plus removing the misleading fallback.

**YouTube videos timing out.** Gemini's video API takes 30–90 seconds per lecture-length video — well past our 40-second notebook deadline. We tried bumping the deadline (slowed everything else), tried `MEDIA_RESOLUTION_LOW` (helped marginally), tried the `VideoMetadata.end_offset` field (turns out it's in the SDK type definitions but not actually supported by the public API). Eventually pivoted to `youtube-transcript-api` as the primary path — fetches the official caption track in ~1 second — with the slow Gemini path as a fallback for caption-less videos.

**Vestigial code from architectural pivots.** Synapse went through two big rewrites — RAG to long-context grounding, and Celery to plain asyncio. Each pivot left behind hundreds of lines of dead code: chunk stores, embedding pipelines, Celery scaffolding, schema migrations for tables nobody used. A late-stage cleanup pass removed ~600 net lines and dropped two dependencies.

**The Cloudflare Workers / Python mismatch.** Originally planned to deploy everything to Cloudflare. Discovered that Workers Python is Pyodide-based with a 30s execution cap, no thread pool, and no support for our `httpx` SSL-context pattern. Pivoted the backend to Fly.io and accepted the architectural split — frontend on Cloudflare for edge speed, backend on Fly.io for full Python.

## Accomplishments we're proud of

- **Sub-60-second pipeline.** Discovery + parallel crawl + summarize + graph for ~10 sources in ~50 seconds.
- **True multi-modal sources.** A single notebook can mix arXiv PDFs, YouTube lectures, news articles, Reddit threads, Twitter posts. Each routed to the right ingest path.
- **The graph is the UI.** Chat answers literally light up the cited nodes — the graph isn't decoration, it's how you navigate the corpus.
- **Cleanup passed.** ~600 LOC of vestigial code removed; the codebase is now smaller than it was 2 weeks ago despite shipping more features.
- **Live deploy on free tiers.** $0/month at hobby usage, frontend at the edge globally, backend cold-starts in 5–10 seconds.

## What we learned

- **Long-context grounding can replace RAG for small corpora** — and the grounding is *stronger* because the model sees full articles instead of retrieved chunks. RAG's complexity is justified when the corpus doesn't fit in context. Our notebooks always fit.
- **Per-platform deployment assumptions matter.** Cloudflare Workers' "every byte runs at the edge" model fundamentally conflicts with our 60-second async pipelines. Fly.io's "Firecracker microVMs that auto-sleep" model fits perfectly. There's no universally-best cloud — you pick based on what your workload looks like.
- **Don't trust SDK type hints alone.** The `VideoMetadata.end_offset` example was a sharp reminder that having a field in `Optional[str]` annotations doesn't mean the API supports it. Test against the live API.
- **Vestigial code accretes faster than you think.** Every architectural pivot left a residue. Quarterly cleanup passes catch them; without that, the codebase grows scarier even as features land.

## What's next for Synapse

- **Multi-notebook UX.** Today each session creates one notebook stored in memory. Support persistent multi-notebook libraries via Supabase.
- **Audio sources.** Add `gemini_ingest_audio` for podcasts and lectures via Gemini's native audio understanding (same pattern as PDFs).
- **Source caching.** SHA256 of normalized text → cached summary + content. Repeat-source hit rate would be high across notebooks on related topics.
- **Citation precision.** Today citations are at source-granularity. Adding chunk-level citation extraction would let the chat answer underline specific quoted sentences.
- **Export.** PNG of the graph; markdown export of the chat history with inline citations; bundled `.json` of the whole notebook for sharing.
