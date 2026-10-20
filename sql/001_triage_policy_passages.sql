-- Vector store for the document-intake triage project.
--
-- Lives in its own `triage` schema so it stays isolated from the application
-- tables (patients, encounters, ...). No PHI is stored here.
--
-- Apply with:  supabase db push   (or paste into the SQL editor)

create schema if not exists extensions;
create extension if not exists vector with schema extensions;

create schema if not exists triage;

create table if not exists triage.policy_passages (
    id          text primary key,
    source      text not null,
    clause      text not null,
    content     text not null,
    embedding   extensions.vector(1536) not null,
    created_at  timestamptz not null default now()
);

create index if not exists policy_passages_embedding_idx
    on triage.policy_passages
    using hnsw (embedding extensions.vector_cosine_ops);

-- RLS on with no policies: anon/public cannot read it. The service role and
-- direct connections bypass RLS by design.
alter table triage.policy_passages enable row level security;

create or replace function triage.match_policy_passages(
    query_embedding extensions.vector(1536),
    match_count int default 3
)
returns table (
    id text,
    source text,
    clause text,
    content text,
    similarity double precision
)
language sql
stable
as $$
    select
        p.id,
        p.source,
        p.clause,
        p.content,
        1 - (p.embedding <=> query_embedding) as similarity
    from triage.policy_passages p
    order by p.embedding <=> query_embedding
    limit match_count;
$$;
