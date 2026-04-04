-- RPC: hybrid_search_chunks
-- Fuses pgvector ANN search with Postgres full-text search using RRF.
-- Requires: source_chunks.fts tsvector column (add_source_chunks_fts.sql)
-- Apply in Supabase Dashboard → SQL Editor.

CREATE OR REPLACE FUNCTION hybrid_search_chunks(
  p_notebook_id     uuid,
  p_query_text      text,
  p_query_embedding vector(768),
  p_match_count     int DEFAULT 10,
  p_rrf_k           int DEFAULT 60
)
RETURNS TABLE(source_id uuid, content text, chunk_index int, rrf_score float8)
LANGUAGE sql STABLE
AS $$
  WITH
    tsq AS (
      SELECT websearch_to_tsquery('english', p_query_text) AS q
    ),
    vec_ranked AS (
      SELECT
        sc.source_id,
        sc.content,
        sc.chunk_index,
        ROW_NUMBER() OVER (ORDER BY sc.embedding <=> p_query_embedding) AS rank
      FROM source_chunks sc
      WHERE sc.notebook_id = p_notebook_id
      ORDER BY sc.embedding <=> p_query_embedding
      LIMIT GREATEST(p_match_count * 3, 20)
    ),
    fts_ranked AS (
      SELECT
        sc.source_id,
        sc.content,
        sc.chunk_index,
        ROW_NUMBER() OVER (
          ORDER BY ts_rank_cd(sc.fts, (SELECT q FROM tsq)) DESC
        ) AS rank
      FROM source_chunks sc
      WHERE sc.notebook_id = p_notebook_id
        AND (SELECT q FROM tsq) IS NOT NULL
        AND sc.fts @@ (SELECT q FROM tsq)
      ORDER BY ts_rank_cd(sc.fts, (SELECT q FROM tsq)) DESC
      LIMIT GREATEST(p_match_count * 3, 20)
    )
  SELECT
    COALESCE(v.source_id,    f.source_id)    AS source_id,
    COALESCE(v.content,      f.content)      AS content,
    COALESCE(v.chunk_index,  f.chunk_index)  AS chunk_index,
    COALESCE(1.0 / (p_rrf_k + v.rank), 0.0)
      + COALESCE(1.0 / (p_rrf_k + f.rank), 0.0)  AS rrf_score
  FROM vec_ranked v
  FULL OUTER JOIN fts_ranked f
    ON v.source_id = f.source_id
   AND v.chunk_index = f.chunk_index
  ORDER BY rrf_score DESC
  LIMIT p_match_count;
$$;
