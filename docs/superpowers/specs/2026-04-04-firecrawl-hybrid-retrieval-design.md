# Firecrawl Integration + Hybrid Retrieval Design

**Date:** 2026-04-04 (revised after code review)
**Scope:** Backend only — `crawler.py`, `rag.py`, `database.py`, `config.py`, `worker.py`, `notebooks.py`, new Supabase migration + RPC

---

## Context

Two gaps limit demo quality today:

1. **PDF crawling is silently broken.** `SourceComposer.jsx` lets users add PDF sources, but `crawler.py:21` lists `application/pdf` in `_SKIP_CONTENT_TYPE_EXACT`, so every PDF URL returns `{"error": ...}`. Additionally, `notebooks.py:24` reads `crawled["text"]` immediately after `crawl_url()` — a truthy error dict causes a `KeyError`. JavaScript-heavy pages also silently return weak text through `trafilatura`.

2. **Retrieval is vector-only.** `rag.py:25` (`retrieve_relevant_sources`) fetches all notebook chunks into Python and scores each with cosine similarity. This misses exact-match and keyword queries where lexical ranking would dominate.

---

## Part 1: Firecrawl Crawler Integration

### PDF detection

`smart_crawl_url()` determines PDF routing via a private helper:

```python
def _looks_like_pdf(url: str, source_type: str) -> bool:
    return source_type == "pdf" or url.lower().split("?")[0].endswith(".pdf")
```

This catches both explicit `source_type="pdf"` (from manually-added sources) and seed URLs that end in `.pdf` (which the notebook creation call site passes without a source_type). A PDF URL that uses neither cue (e.g., a redirect) falls into the webpage path and reaches Firecrawl only on fallback — this is acceptable and stated explicitly below.

### Routing logic

```
_looks_like_pdf() == True  → Firecrawl first; return None if Firecrawl fails
webpage URL                → crawl_url() (httpx + trafilatura) first
                             → fallback to Firecrawl if:
                                 result is None, has "error" key, or
                                 len(result["text"].strip()) < firecrawl_fallback_min_chars
                             → if Firecrawl also fails, return weak primary result
                               only if len(text.strip()) >= firecrawl_fallback_min_chars;
                               otherwise None
```

`smart_crawl_url()` always returns either `{"text": ..., "title": ...}` or `None`. It never returns a structured error dict. Both call sites can safely check `if not result` without further inspection.

**When `firecrawl-py` is absent or `FIRECRAWL_API_KEY` is unset:**
- PDF URLs → `None` (unsupported; no fallback available)
- Webpage URLs with weak extraction (< `firecrawl_fallback_min_chars` chars) → the weak primary result is returned as-is (not `None`), since no Firecrawl retry is available
- Webpage URLs with None or error result → `None`

This is a deliberate behaviour change from current (which returns structured errors); it is explicitly not a "soft fallback" to the full current behaviour.

### `config.py` — 2 new fields

```python
firecrawl_api_key: Optional[str] = os.getenv("FIRECRAWL_API_KEY")
firecrawl_fallback_min_chars: int = int(os.getenv("FIRECRAWL_FALLBACK_MIN_CHARS", "200"))
```

### `crawler.py` — 3 additions

**Optional import at module level (same pattern as `trafilatura` and `google.genai`):**
```python
try:
    from firecrawl import AsyncFirecrawlApp
except Exception:
    AsyncFirecrawlApp = None
```

**`crawl_url_with_firecrawl(url)`**
- Returns `None` immediately if `AsyncFirecrawlApp is None` or `settings.firecrawl_api_key` is absent
- Uses `AsyncFirecrawlApp` (native async — no `run_in_executor` needed)
- Calls `await app.scrape_url(url, formats=["markdown"])` — verify exact method name against pinned package version; `scrape_url` is the current SDK method but may become `scrape` in future major releases
- Returns `{"text": result.markdown[:max_document_chars], "title": result.metadata.title or url}` or `None`
- Catches all exceptions, logs, returns `None`

**`_looks_like_pdf(url, source_type)`** — private helper, no I/O.

**`smart_crawl_url(url, source_type="webpage")`**
- Implements routing table above
- Always returns `{"text": ..., "title": ...}` or `None`

### Call site changes

| File | Line | Before | After |
|---|---|---|---|
| `notebooks.py` | 12, 24 | `from ... import crawl_url` / `crawl_url(req.seed_url)` | `smart_crawl_url` / `smart_crawl_url(req.seed_url)` |
| `worker.py` | 172, 222 | `from ... import crawl_url` / `crawl_url(record["url"])` | `smart_crawl_url` / `smart_crawl_url(record["url"], record.get("source_type", "webpage"))` |

### Dependency

`firecrawl-py` added to `backend/requirements.txt`. Import is optional — package absence degrades behaviour as described above.

---

## Part 2: Hybrid Retrieval (Supabase FTS + pgvector + RRF)

### Schema migration — `backend/migrations/add_source_chunks_fts.sql`

```sql
ALTER TABLE source_chunks
  ADD COLUMN fts tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

CREATE INDEX source_chunks_fts_idx ON source_chunks USING GIN(fts);
```

The `GENERATED ALWAYS ... STORED` column backfills on existing rows automatically. New chunks get the column populated on insert.

### Supabase RPC — `hybrid_search_chunks`

Signature:
```sql
hybrid_search_chunks(
  p_notebook_id     uuid,
  p_query_text      text,
  p_query_embedding vector(768),
  p_match_count     int DEFAULT 10,
  p_rrf_k           int DEFAULT 60
)
RETURNS TABLE(source_id uuid, content text, chunk_index int, rrf_score float8)
```

Logic:
```sql
WITH
  tsq AS (
    SELECT websearch_to_tsquery('english', p_query_text) AS q
  ),
  vec_ranked AS (
    SELECT source_id, content, chunk_index,
           ROW_NUMBER() OVER (ORDER BY embedding <=> p_query_embedding) AS rank
    FROM source_chunks
    WHERE notebook_id = p_notebook_id
    ORDER BY embedding <=> p_query_embedding
    LIMIT GREATEST(p_match_count * 3, 20)
  ),
  fts_ranked AS (
    SELECT source_id, content, chunk_index,
           ROW_NUMBER() OVER (ORDER BY ts_rank_cd(fts, (SELECT q FROM tsq)) DESC) AS rank
    FROM source_chunks
    WHERE notebook_id = p_notebook_id
      AND (SELECT q FROM tsq) IS NOT NULL
      AND fts @@ (SELECT q FROM tsq)
    ORDER BY ts_rank_cd(fts, (SELECT q FROM tsq)) DESC
    LIMIT GREATEST(p_match_count * 3, 20)
  )
SELECT
  COALESCE(v.source_id,   f.source_id)   AS source_id,
  COALESCE(v.content,     f.content)     AS content,
  COALESCE(v.chunk_index, f.chunk_index) AS chunk_index,
  COALESCE(1.0 / (p_rrf_k + v.rank), 0.0)
    + COALESCE(1.0 / (p_rrf_k + f.rank), 0.0) AS rrf_score
FROM vec_ranked v
FULL OUTER JOIN fts_ranked f
  ON v.source_id = f.source_id AND v.chunk_index = f.chunk_index
ORDER BY rrf_score DESC
LIMIT p_match_count;
```

Note: CTEs named `vec_ranked` / `fts_ranked` to avoid visual ambiguity with the `fts` tsvector column on `source_chunks`.

**Edge-case guards built into the query:**
- If `p_query_text` collapses to all stopwords, `websearch_to_tsquery` returns `NULL`. The `fts_ranked` CTE's `WHERE` clause short-circuits to no rows. The FULL OUTER JOIN leaves `vec_ranked` results intact — vector ranking stands alone.
- If FTS returns no rows (no lexical matches), the FULL OUTER JOIN still returns all `vec_ranked` results with `fts_component = 0`. No failure.
- Candidate count per side is `GREATEST(p_match_count * 3, 20)` — generous enough to feed the Python-side per-source grouping without being unbounded.

### `database.py` — new method + module-level function

**`SupabaseRepository.hybrid_search_chunks(notebook_id, query_text, query_embedding, match_count)`**
```python
result = self._client.rpc("hybrid_search_chunks", {
    "p_notebook_id": notebook_id,
    "p_query_text": query_text,
    "p_query_embedding": query_embedding,
    "p_match_count": match_count,
}).execute()
return result.data
```

**`InMemoryRepository.hybrid_search_chunks(...)`** — falls back to cosine-only (sufficient for tests; no FTS in memory). Must coerce embeddings before scoring (see below).

**Module-level:** `async def hybrid_search_chunks(notebook_id, query_text, query_embedding, match_count)` delegates to the repository.

### `rag.py` — `retrieve_relevant_sources` refactored

**New private helper `_coerce_and_score_chunks(chunks, query_embedding, settings)`:**
- Accepts a list of chunk dicts (from either `hybrid_search_chunks` fallback or `get_notebook_chunks`)
- Coerces each embedding: `emb = [float(v) for v in (chunk.get("embedding") or [])]` — handles Supabase pgvector strings and list-of-strings
- Scores with `cosine_similarity(query_embedding, emb)`
- Returns sorted results capped at `settings.rag_max_chunks` total, respecting `settings.rag_max_chunks_per_source`

**New retrieval flow:**
```
embed query (unchanged)
→ hybrid_search_chunks(notebook_id, query, query_embedding, rag_max_chunks * 3)
→ Python side: group by source_id, apply rag_max_chunks_per_source,
               enforce rag_max_chunks global cap, cap sources at top_k
→ on any exception: log warning, call _coerce_and_score_chunks(
    await get_notebook_chunks(notebook_id), query_embedding, settings
  ) as the fallback — this path always coerces embeddings before scoring
```

**Chunk cap preservation:** The post-RPC grouping loop must enforce both caps:
- `rag_max_chunks_per_source` chunks per source (as today)
- `rag_max_chunks` total chunks across all sources (currently enforced at `rag.py:73` — preserve this)

Exceeding `top_k * rag_max_chunks_per_source > rag_max_chunks` would otherwise grow the context window silently.

**The "no chunks" path** (no Supabase or `notebook_id` absent) stays unchanged — source-level cosine retrieval as today.

---

## Testing requirements

1. **Seed PDF routing** — notebook creation test: POST with a `seed_url` ending in `.pdf`, mock `crawl_url_with_firecrawl` to return content. Assert no `KeyError`, assert Firecrawl was called (not `crawl_url`).

2. **Weak extraction + Firecrawl absent** — crawler test: `crawl_url()` returns 80-char result, `AsyncFirecrawlApp is None`. Assert `smart_crawl_url()` returns the weak result (not `None`) for webpage source_type.

3. **Supabase string embeddings in fallback** — retrieval test: mock `hybrid_search_chunks` to raise, mock `get_notebook_chunks` to return chunks with embeddings as pgvector-style strings (`"[0.1,0.2,...]"`). Assert fallback returns ranked results (not zeros or errors).

4. **Stopword-only query** — retrieval integration test: query text collapses to empty tsquery. Assert RPC returns vector-ranked results (not empty list).

---

## What does NOT change

- `crawl_url()` signature and behavior — untouched; existing tests stay valid
- `InMemoryRepository` correctness for unit tests — hybrid falls back to cosine-only with embedding coercion
- Frontend — no changes
- Celery pipeline stages — only the crawl import and one call site change in Stage 3
