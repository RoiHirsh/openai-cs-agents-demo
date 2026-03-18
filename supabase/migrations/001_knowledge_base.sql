-- Migration: 001_knowledge_base
-- Creates the qa_pairs and handoff_triggers tables for the internal knowledge base system.
-- Replaces the OpenAI vector store (PDF-based) approach.
--
-- Prerequisites:
--   - pgvector extension must be available (Supabase includes it by default)
--   - Run this in the Supabase SQL editor or via the Supabase CLI:
--       supabase db push  (if using CLI with supabase/migrations folder linked)
--     OR paste the full contents into the Supabase dashboard → SQL Editor → Run

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Enable pgvector
-- ─────────────────────────────────────────────────────────────────────────────
create extension if not exists vector;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Tables
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists qa_pairs (
    id             uuid        primary key default gen_random_uuid(),
    question       text        not null,
    answer         text        not null,
    embedding      vector(1536),
    active         boolean     not null default true,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);

create table if not exists handoff_triggers (
    id               uuid        primary key default gen_random_uuid(),
    scenario         text        not null,
    default_response text        not null default 'אחד רגע בבקשה 🙏',
    embedding        vector(1536),
    active           boolean     not null default true,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. HNSW indexes for fast cosine similarity search
--    (hnsw works well at any table size, including small ones like 20–200 rows)
-- ─────────────────────────────────────────────────────────────────────────────
create index if not exists qa_pairs_embedding_idx
    on qa_pairs using hnsw (embedding vector_cosine_ops);

create index if not exists handoff_triggers_embedding_idx
    on handoff_triggers using hnsw (embedding vector_cosine_ops);

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. updated_at auto-update trigger
-- ─────────────────────────────────────────────────────────────────────────────
create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create or replace trigger qa_pairs_updated_at
    before update on qa_pairs
    for each row execute function set_updated_at();

create or replace trigger handoff_triggers_updated_at
    before update on handoff_triggers
    for each row execute function set_updated_at();

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. RPC functions for semantic search
--    Both use cosine similarity via pgvector's <=> operator.
--    similarity = 1 - cosine_distance (range: -1 to 1, higher = more similar)
-- ─────────────────────────────────────────────────────────────────────────────

-- Thresholds used by the agent (defined here for reference):
--   qa_pairs:          match_threshold = 0.78, match_count = 3
--   handoff_triggers:  match_threshold = 0.82, match_count = 1

create or replace function match_qa_pairs(
    query_embedding  vector(1536),
    match_threshold  float,
    match_count      int
)
returns table (
    id          uuid,
    question    text,
    answer      text,
    similarity  float
)
language sql stable as $$
    select
        id,
        question,
        answer,
        1 - (embedding <=> query_embedding) as similarity
    from qa_pairs
    where active = true
      and 1 - (embedding <=> query_embedding) >= match_threshold
    order by embedding <=> query_embedding
    limit match_count;
$$;

create or replace function match_handoff_triggers(
    query_embedding  vector(1536),
    match_threshold  float,
    match_count      int
)
returns table (
    id               uuid,
    scenario         text,
    default_response text,
    similarity       float
)
language sql stable as $$
    select
        id,
        scenario,
        default_response,
        1 - (embedding <=> query_embedding) as similarity
    from handoff_triggers
    where active = true
      and 1 - (embedding <=> query_embedding) >= match_threshold
    order by embedding <=> query_embedding
    limit match_count;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. Row Level Security
--    Service role key (used by agent backend): full access
--    Anon key: read-only (dashboard reads go through agent API, not direct Supabase)
-- ─────────────────────────────────────────────────────────────────────────────
alter table qa_pairs enable row level security;
alter table handoff_triggers enable row level security;

-- qa_pairs policies
create policy "qa_pairs_service_role_all"
    on qa_pairs for all
    using (auth.role() = 'service_role');

create policy "qa_pairs_anon_read"
    on qa_pairs for select
    using (auth.role() = 'anon');

-- handoff_triggers policies
create policy "handoff_triggers_service_role_all"
    on handoff_triggers for all
    using (auth.role() = 'service_role');

create policy "handoff_triggers_anon_read"
    on handoff_triggers for select
    using (auth.role() = 'anon');
