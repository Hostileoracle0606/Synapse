-- Migration: add tsvector FTS column + GIN index to source_chunks
-- Apply in Supabase Dashboard → SQL Editor, then run rpc_hybrid_search_chunks.sql

ALTER TABLE source_chunks
  ADD COLUMN IF NOT EXISTS fts tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

CREATE INDEX IF NOT EXISTS source_chunks_fts_idx
  ON source_chunks USING GIN(fts);
