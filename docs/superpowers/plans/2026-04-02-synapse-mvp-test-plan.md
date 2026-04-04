# Synapse MVP Test Plan

## Automated now

- Backend config parsing, model validation, in-memory repository behavior, source chunk storage/replacement, chunk replacement isolation, chunking behavior, chunk embedding assembly, chunk-based retrieval fallbacks, retrieval caps per source/total, graph centroid generation, API route success/error paths, and the FastAPI health/OpenAPI smoke checks.
- These tests are stable without live Gemini, Supabase, Redis, or network access because the implementation already has in-memory and fallback paths.

## Deferred or manual for MVP

- Frontend component rendering, notebook polling, graph interactions, and chat UX.
- End-to-end notebook creation against a real backend plus live Gemini grounding and Supabase storage.
- Load/performance validation once notebook-level chunk counts grow beyond MVP scale.

## Gap

- Frontend component tests remain deferred; the current automated coverage is backend-heavy and does not yet validate the full browser chat/graph experience.
