create extension if not exists vector;

create table if not exists notebooks (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  seed_url text,
  seed_text text,
  status text not null default 'discovering',
  created_at timestamptz default now()
);

create table if not exists sources (
  id uuid primary key default gen_random_uuid(),
  notebook_id uuid references notebooks(id) on delete cascade,
  url text,
  title text not null,
  source_type text not null default 'webpage',
  summary text,
  content text,
  embedding vector(768), -- source-level centroid (unused for edge computation but retained for compatibility)
  status text not null default 'pending',
  error_message text,
  created_at timestamptz default now()
);

create table if not exists source_chunks (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references sources(id) on delete cascade,
  notebook_id uuid not null references notebooks(id) on delete cascade,
  chunk_index integer not null,
  content text not null,
  char_start integer not null,
  char_end integer not null,
  embedding vector(768) not null,
  created_at timestamptz default now(),
  unique(source_id, chunk_index)
);

create table if not exists edges (
  id uuid primary key default gen_random_uuid(),
  notebook_id uuid references notebooks(id) on delete cascade,
  source_a uuid references sources(id) on delete cascade,
  source_b uuid references sources(id) on delete cascade,
  similarity float not null,
  relationship text,
  unique(source_a, source_b, notebook_id)
);

create table if not exists messages (
  id uuid primary key default gen_random_uuid(),
  notebook_id uuid references notebooks(id) on delete cascade,
  role text not null,
  content text not null,
  sources_cited uuid[],
  created_at timestamptz default now()
);

create index if not exists sources_embedding_idx
  on sources using ivfflat (embedding vector_cosine_ops) with (lists = 100);

create index if not exists source_chunks_embedding_idx
  on source_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);

create index if not exists sources_notebook_idx on sources (notebook_id);
create index if not exists source_chunks_source_idx on source_chunks (source_id);
create index if not exists source_chunks_notebook_idx on source_chunks (notebook_id);
create index if not exists edges_notebook_idx on edges (notebook_id);
create index if not exists messages_notebook_idx on messages (notebook_id);

-- Migration 2026-04-04: FTS column for hybrid retrieval
-- Run backend/migrations/add_source_chunks_fts.sql then
-- backend/migrations/rpc_hybrid_search_chunks.sql in Supabase SQL Editor.
alter table source_chunks
  add column if not exists fts tsvector
    generated always as (to_tsvector('english', content)) stored;

create index if not exists source_chunks_fts_idx
  on source_chunks using gin(fts);

-- RPC for hybrid retrieval (see backend/migrations/rpc_hybrid_search_chunks.sql)
-- Abbreviated here; run the full file from Supabase SQL Editor.

-- Migration: downgrade from vector(3072) back to vector(768)
-- Run these statements in the Supabase SQL editor (Table Editor → SQL).
-- Existing 3072-dimension rows must be cleared first (truncate or delete),
-- as pgvector does not allow in-place dimension changes.
--
--   truncate table source_chunks cascade;
--   truncate table sources cascade;
--   drop index if exists sources_embedding_idx;
--   drop index if exists source_chunks_embedding_idx;
--   alter table sources alter column embedding type vector(768);
--   alter table source_chunks alter column embedding type vector(768);
--   create index if not exists sources_embedding_idx
--     on sources using ivfflat (embedding vector_cosine_ops) with (lists = 100);
--   create index if not exists source_chunks_embedding_idx
--     on source_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);
