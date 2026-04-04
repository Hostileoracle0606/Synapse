# Synapse Bug Fixes & Hardening — Design Spec
**Date:** 2026-04-03
**Approach:** Severity-tiered (Tier 1 → Tier 2 → Tier 3), automated tests after each tier

---

## Overview

Fix 13 identified issues across the knowledge base pipeline and graph renderer, grouped by severity. Each tier is fully tested before the next begins. All fixes include anticipatory/defensive measures to prevent bad data from propagating rather than only catching it after the fact.

---

## Tier 1 — Data Integrity

### 1.1 Edge Upsert Collision (`database.py`, `supabase_schema.sql`)

**Problem:** `on_conflict="source_a,source_b"` allows edges from different notebooks to overwrite each other.

**Fix:**
- Change conflict key to `"source_a,source_b,notebook_id"` in `SupabaseRepository.upsert_edge()`
- Add matching unique constraint to `supabase_schema.sql`
- Fix `InMemoryRepository` edge deduplication to also key on `(source_a, source_b, notebook_id)`

**Anticipation:**
- Validate `source_a`, `source_b`, `notebook_id` are non-null UUIDs before upsert — fail fast
- Assert `source_a != source_b` — reject self-edges before they reach the DB

---

### 1.2 Centroid Skipping Mismatched Embeddings (`graph.py`, `processor.py`)

**Problem:** `centroid_from_chunk_embeddings()` silently skips wrong-dimension embeddings, producing biased centroids.

**Fix:**
- Log a warning when a chunk embedding is skipped
- If >10% of chunks are wrong-dimension, raise an error (indicates data corruption)
- If ≤10%, log and skip, produce centroid from valid chunks

**Anticipation:**
- Validate embedding dimensions at write time in `processor.py` when chunks come back from the Gemini API
- Wrong-dimension embeddings are rejected before storage — centroid computation never sees corrupt data
- On dimension mismatch per chunk, mark that chunk failed and continue with remaining chunks

---

### 1.3 `process_source_content()` Error Handling (`worker.py`)

**Problem:** Zero error handling — any exception crashes the Celery task silently; source stays stuck in `"processing"`.

**Fix:**
- Wrap `summarize_document()` and `embed_chunks()` in try-except
- On failure: mark source `"error"`, save error message to `sources.error_message`, re-raise for Celery logging
- Fix outer `except Exception` in `process_notebook` to log which step failed before setting notebook `"error"`

**Anticipation:**
- Validate input before calling APIs: reject empty/whitespace-only text, reject text under 100 chars
- Add exponential backoff retry (3 attempts, 1s/2s/4s) for transient errors (`httpx.TimeoutException`, Gemini rate-limit) before marking as error

---

### Tier 1 Tests

| Test | Assertion |
|------|-----------|
| `test_edge_upsert_isolation` | Two notebooks with same source pair → each retains its own similarity value |
| `test_self_edge_rejected` | `source_a == source_b` raises before hitting DB |
| `test_embedding_dim_validated_at_write` | Wrong-dim embed from API → chunk marked failed, source continues |
| `test_centroid_mismatched_dims` | Mixed-dim embeddings → warning logged, correct centroid from valid chunks |
| `test_centroid_majority_corrupt` | >10% wrong-dim → raises error |
| `test_process_source_content_summarize_failure` | `summarize_document` raises → source marked `"error"` with message |
| `test_process_source_content_embed_failure` | `embed_chunks` raises → source marked `"error"` with message |
| `test_short_content_rejected_early` | 50-char text → rejected before any API call |
| `test_retry_on_transient_api_error` | Gemini fails twice then succeeds → source ends up `"ready"` |

---

## Tier 2 — Correctness

### 2.1 Crawler HTML Fallback (`crawler.py`)

**Problem:** Fallback returns raw HTML (including `<script>`, `<style>`) which pollutes embeddings.

**Fix:**
- Replace `_fallback_result(url, html)` with a stripping pass using Python's stdlib `html.parser`
- If stripped result is still <50 chars, return a structured failure result (empty content, `status="error"`)

**Anticipation:**
- Check `Content-Type` header before fetching body — skip non-text types (`image/*`, `application/pdf`, etc.) immediately without downloading

---

### 2.2 Discovery Fallback Returns Search URLs (`discovery.py`)

**Problem:** When Gemini is unavailable, fallback returns Google/Scholar/News search URLs that produce junk sources.

**Fix:**
- Remove the search URL fallback entirely
- Return empty list `[]` when Gemini unavailable; worker marks notebook `"error"` with `"Discovery unavailable: Gemini API not configured"`

**Anticipation:**
- Validate discovered URLs before returning: filter out search engine domains, social media, and known non-content domains (`google.com`, `twitter.com`, etc.)

---

### 2.3 Synchronous Celery Fallback Blocks API (`worker.py`)

**Problem:** If Redis/Celery is down, `enqueue_notebook_processing` runs the full pipeline synchronously, blocking the API request.

**Fix:**
- Remove `run_async(process_notebook(...))` fallback
- If Celery/Redis down, mark notebook `"error"` with `"Task queue unavailable"` and return

**Anticipation:**
- Add Celery broker health check at app startup (`main.py`), expose via `/health` endpoint — fail loudly at boot

---

### 2.4 `TypeError` Catch Masking Design Flaw (`worker.py`)

**Problem:** Broad `except TypeError` works around a `compute_edges()` signature mismatch, hiding real bugs.

**Fix:**
- Align `compute_edges()` to a single signature accepting both docs and optional chunks
- Delete the `except TypeError` fallback block entirely

---

### 2.5 Config Values Not Wired Up (`worker.py`, `rag.py`, `config.py`)

**Problem:** `max_discovery_results`, edge threshold, and RAG limits are hardcoded despite config definitions existing.

**Fix:**
- `worker.py:78` → `settings.max_discovery_results`
- `worker.py:117,121` → `settings.edge_similarity_threshold` (add to `config.py`, default `0.4`)
- `rag.py:68-73` → `settings.rag_max_chunks` (default `8`), `settings.rag_max_chunks_per_source` (default `2`)

---

### Tier 2 Tests

| Test | Assertion |
|------|-----------|
| `test_crawler_fallback_strips_html` | Trafilatura failure → output has no HTML tags |
| `test_crawler_skips_non_text_content_type` | `Content-Type: image/png` → source skipped, no body fetch |
| `test_discovery_empty_on_no_gemini` | Gemini unavailable → returns `[]`, not search URLs |
| `test_discovery_filters_search_domains` | Gemini returns `google.com` URL → filtered out |
| `test_enqueue_fails_cleanly_without_celery` | Redis down → notebook marked `"error"`, no blocking |
| `test_compute_edges_single_signature` | `compute_edges` works with and without chunks arg, no TypeError |
| `test_config_values_propagate` | `max_discovery_results` from env flows to discovery; threshold flows to graph; RAG limits flow to retrieval |

---

## Tier 3 — UX / Completeness

### 3.1 Graph Simulation Stability (`DocumentWeb.jsx`)

**Problem:** d3 simulation torn down and rebuilt on every 3-second poll, causing constant layout resets.

**Fix (stable refs approach):**
- Move simulation into `useRef` — created once on mount, never recreated
- On incoming node/edge changes, diff against simulation's current state
- Add new nodes at centroid of connected neighbors (not random positions)
- Remove departed nodes/edges from the running simulation
- When new nodes added, reheat simulation with `alpha(0.3)` rather than restarting
- Move `liveNodeMap` into a `useRef` updated only when nodes change

**Anticipation:**
- Guard every link render: null-check source/target before rendering `<line>`
- Clamp `similarity` to `[0, 1]` before applying to stroke — prevents NaN/invalid SVG attributes

---

### 3.2 Relationship Labels Not Displayed (`DocumentWeb.jsx`)

**Problem:** Backend generates edge relationship labels but frontend never shows them.

**Fix:**
- Render edge labels as SVG `<text>` at line midpoint, visible on hover via CSS opacity transition
- Truncate to 40 chars with ellipsis
- Only render when simulation alpha < 0.1 (settled) to avoid jitter during layout

---

### 3.3 Edge Label Batch Limit (`graph.py`)

**Problem:** Only first 20 edges get AI-generated labels; the rest default to `"related topics"`.

**Fix:**
- Replace `edges[:20]` with configurable `settings.edge_label_batch_size` (default `20`, add to `config.py`)
- Process remaining edges in additional batches rather than defaulting them
- Guard: if Gemini response returns fewer labels than batch size, fill remaining with `"related topics"` rather than crashing

**Anticipation:**
- Validate Gemini label response is a list of expected length before applying — if malformed, fall back per-edge

---

### Tier 3 Tests

| Test | Assertion |
|------|-----------|
| `test_graph_simulation_persists_across_rerender` | 3 nodes rendered, 4th added → simulation ref is same object, first 3 retain x/y |
| `test_new_node_placed_near_neighbors` | New node connected to existing → initial position within 100px of neighbor |
| `test_edge_renders_with_null_similarity` | Edge with `similarity: null` → `<line>` renders with fallback values, no NaN attributes |
| `test_relationship_label_renders_at_midpoint` | `<text>` element at `(x1+x2)/2, (y1+y2)/2` for each edge |
| `test_edge_label_batch_processes_all_edges` | 35 edges → all 35 get non-default labels (not just first 20) |
| `test_edge_label_malformed_response` | Gemini returns 5 labels for 10-edge batch → no crash, remaining 5 get `"related topics"` |

---

## Files Changed Summary

| File | Tier | Type of Change |
|------|------|---------------|
| `backend/app/database.py` | 1 | Edge upsert conflict key + self-edge validation |
| `backend/supabase_schema.sql` | 1 | Unique constraint on `(source_a, source_b, notebook_id)` |
| `backend/app/services/graph.py` | 1, 3 | Centroid validation; edge label batching |
| `backend/app/services/processor.py` | 1 | Embedding dimension validation at write time |
| `backend/app/worker.py` | 1, 2 | Error handling, retry, config wiring, TypeError fix, Celery fallback |
| `backend/app/services/crawler.py` | 2 | HTML stripping, Content-Type guard |
| `backend/app/services/discovery.py` | 2 | Remove search URL fallback, URL validation |
| `backend/app/config.py` | 2, 3 | Add `edge_similarity_threshold`, `rag_max_chunks`, `rag_max_chunks_per_source`, `edge_label_batch_size` |
| `backend/app/services/rag.py` | 2 | Wire config values |
| `backend/app/main.py` | 2 | Celery health check + `/health` endpoint |
| `frontend/src/components/DocumentWeb.jsx` | 3 | Stable sim refs, incremental updates, edge labels |
| `backend/tests/` | 1-3 | 22 new tests across all tiers |
