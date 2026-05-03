-- Synapse Supabase schema (optional path).
--
-- Set SUPABASE_URL + SUPABASE_KEY env vars to activate this. Otherwise
-- the backend uses the in-memory repository (state lost on restart, fine
-- for hobby deploys).
--
-- This schema is the bare minimum the current backend needs. Run it in
-- the Supabase SQL editor or via `psql -f supabase_schema.sql`.

create table if not exists notebooks (
    id          uuid primary key default gen_random_uuid(),
    title       text not null,
    seed_url    text,
    seed_text   text,
    status      text not null default 'discovering',
    created_at  timestamptz not null default now()
);

create table if not exists sources (
    id              uuid primary key default gen_random_uuid(),
    notebook_id     uuid not null references notebooks(id) on delete cascade,
    url             text,
    title           text,
    source_type     text not null default 'webpage',
    summary         text,
    content         text,
    status          text not null default 'pending',
    error_message   text,
    created_at      timestamptz not null default now()
);
create index if not exists sources_notebook_id_idx on sources(notebook_id);

create table if not exists edges (
    id              uuid primary key default gen_random_uuid(),
    notebook_id     uuid not null references notebooks(id) on delete cascade,
    source_a        uuid not null references sources(id) on delete cascade,
    source_b        uuid not null references sources(id) on delete cascade,
    similarity      numeric not null,
    relationship    text
);
create index if not exists edges_notebook_id_idx on edges(notebook_id);

create table if not exists messages (
    id              uuid primary key default gen_random_uuid(),
    notebook_id     uuid not null references notebooks(id) on delete cascade,
    role            text not null,
    content         text not null,
    sources_cited   text[] not null default '{}',
    created_at      timestamptz not null default now()
);
create index if not exists messages_notebook_id_idx on messages(notebook_id);
