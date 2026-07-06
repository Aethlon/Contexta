# 15 — Retrieval Deep Dive

This document specifies how contexta retrieval actually works, why it is fast, and how it stays accurate as a tenant grows. It supersedes the retrieval section in [05-database-strategy.md](./05-database-strategy.md) for implementation detail; that doc remains the source of truth for schema and indexes.

The current `RetrievalEngine` in `contexta/core/retrieval/engine.py` is a correct reference implementation but is not what runs in production. Production retrieval lives in the Go data plane and is structured as a four-stage pipeline.

## Decisions of record

1. **Retrieval is a four-stage pipeline**, not a single SQL query. Stages: candidate generation, hybrid scoring, graph expansion, optional rerank. Each stage has a clear contract and a kill switch.
2. **Candidate generation is bucket-aware.** We never run vector search across an entire tenant's memories. We restrict by `(organization_id, user_id, memory_state ∈ {active, warm}, memory_type filter, valid_to IS NULL)` first.
3. **Cluster-first retrieval.** When the query maps to a known cluster (via embedding proximity to cluster centroids), we search inside the cluster before falling back to global within-tenant search.
4. **Graph expansion is one extra hop max in v1.** More hops degrade quality more than they help. Configurable per request, capped at 3.
5. **LLM rerank is opt-in, not default.** Default retrieval is sub-100 ms p99. Rerank doubles latency and only helps when top-K precision matters.
6. **Replica reads, primary writes.** Hot reads always hit the replica via PgBouncer.
7. **No global vector search across tenants ever.** Cross-tenant queries do not exist.


## The four-stage pipeline

```
                    Query (text + filters + token_budget + rerank?)
                                      │
                                      ▼
        ┌─────────────────────────────────────────────────────┐
        │  Stage 0: Query understanding                        │
        │   - Embed query (parallel with stages 1a/1b)         │
        │   - Detect entity mentions (NER on cached entities)  │
        │   - Optional: HyDE expansion if query < 4 tokens     │
        │   - Resolve seed entities to seed_entity_ids[]       │
        └────────────────────┬────────────────────────────────┘
                             │
                             ▼
        ┌─────────────────────────────────────────────────────┐
        │  Stage 1: Candidate generation (3 parallel paths)    │
        │                                                      │
        │   1a. Cluster-scoped semantic search (top 100)       │
        │       → if matched cluster centroids, search inside  │
        │   1b. Tenant-scoped semantic search (top 200)        │
        │       → fallback / supplement                        │
        │   1c. Keyword search (top 100, tsvector @@ query)    │
        │   1d. Graph-seeded retrieval (memories linked to     │
        │       seed entities, depth ≤ N)                      │
        │                                                      │
        │   Merge into candidate set (dedup by memory_id)      │
        └────────────────────┬────────────────────────────────┘
                             │
                             ▼
        ┌─────────────────────────────────────────────────────┐
        │  Stage 2: Hybrid scoring                             │
        │                                                      │
        │   For each candidate compute weighted score using    │
        │   Reciprocal Rank Fusion (RRF) over the rank lists,  │
        │   plus signal-weighted modifiers:                    │
        │     0.40 semantic                                    │
        │     0.25 graph                                       │
        │     0.20 importance                                  │
        │     0.10 recency                                     │
        │     0.05 keyword                                     │
        │     -0.30 cold-state penalty                         │
        │     +0.10 same-cluster boost                         │
        │     -0.50 archived (if include_archived false)       │
        │                                                      │
        │   Truncate to top 50 candidates                      │
        └────────────────────┬────────────────────────────────┘
                             │
                             ▼
        ┌─────────────────────────────────────────────────────┐
        │  Stage 3: Diversification                            │
        │                                                      │
        │   - MMR (Maximal Marginal Relevance) λ=0.7           │
        │   - Cap memories per entity (max 3)                  │
        │   - Cap memories per memory_type (max 8)             │
        │   - Truncate to query.limit (default 20)             │
        └────────────────────┬────────────────────────────────┘
                             │
                             ▼
        ┌─────────────────────────────────────────────────────┐
        │  Stage 4: Optional LLM rerank (only if rerank=true)  │
        │                                                      │
        │   - Send top 50 (titles+content) + query to LLM      │
        │   - Receive new ordering                             │
        │   - Truncate to query.limit                          │
        │                                                      │
        │   Latency: +400-700ms                                │
        │   Counted as 1 rerank for billing                    │
        └────────────────────┬────────────────────────────────┘
                             │
                             ▼
                       Final results
```


## Stage 0 — Query understanding

### Query embedding

Embedding latency dominates query embed time (~30-60ms via OpenAI, ~3ms via local cache). We:

1. **Cache embeddings of common queries** in Redis with 1-hour TTL keyed by `sha256(query_text)`. Hit rate is high for repetitive agent loops.
2. **Run embedding in parallel** with keyword tokenization and entity detection. The data plane fires the OpenAI embed call as soon as the request is parsed; by the time we issue the SQL we have the vector.

```go
// pseudocode
embChan := make(chan []float32, 1)
go func() {
    if cached, ok := s.cache.Get(queryHash); ok {
        embChan <- cached
        return
    }
    emb, _ := s.embeddings.Embed(ctx, queryText)
    s.cache.Set(queryHash, emb, 1*time.Hour)
    embChan <- emb
}()

// Run keyword + entity detection here, in parallel...

queryEmb := <-embChan
// Now run SQL
```

### Entity mention detection

We do not run a heavy NER model on every query. Instead, the data plane keeps a per-tenant **entity name cache** in Redis (refreshed every 5 minutes from `SELECT name, id FROM entity WHERE organization_id=$1 AND status='active'`). We check the query against the cache using:

1. Exact substring match on entity names (case-insensitive).
2. For >2 word entity names, also fuzzy match (Levenshtein ratio > 0.85).

The matched entity IDs become `seed_entity_ids` for Stage 1d.

This is intentionally cheap (sub-millisecond) and stays accurate for agent workflows where entity names are repeated.

### Query expansion (HyDE)

For very short queries (< 4 tokens), the SDK or data plane can generate a Hypothetical Document Embedding via the LLM:

```
Query: "Postgres?"
HyDE prompt: "Write a one-sentence factual statement about: Postgres?"
HyDE response: "PostgreSQL is the database the user prefers for relational data."
Embedding: embed(HyDE response)
```

HyDE is opt-in via `expand_query=true` and counts as a small LLM call (cheap because output is one sentence).

Default off. We turn it on for tenants whose query mix is dominated by short queries (we can detect this from telemetry).


## Stage 1 — Candidate generation

### 1a. Cluster-scoped semantic search

Each `semantic_cluster` row stores a **centroid embedding** computed as the mean of member memory embeddings, recomputed when membership changes. Centroids live in a small `cluster_centroid` table with HNSW index.

When a query arrives:

```sql
-- Find top 3 matching clusters
SELECT cluster_id
FROM cluster_centroid
WHERE organization_id = $1 AND user_id = $2
ORDER BY centroid <=> $3::vector
LIMIT 3;
```

Then search inside those clusters:

```sql
SELECT m.id, 1 - (m.embedding <=> $1::vector) AS sem_score
FROM memory_record m
JOIN cluster_membership cm ON cm.memory_id = m.id
WHERE cm.cluster_id = ANY($2)
  AND m.organization_id = $3 AND m.user_id = $4
  AND m.valid_to IS NULL AND m.is_archived = false
  AND m.memory_state IN ('active', 'warm')
ORDER BY m.embedding <=> $1::vector
LIMIT 100;
```

Why cluster-first matters: a tenant with 2M memories and 200 clusters means each cluster averages 10k memories. Searching 30k memories (3 clusters) is faster than searching 2M, and the recall is *higher* because the cluster routing is itself a learned signal.

If the top cluster centroid distance > 0.4 (poor match), we skip cluster routing and go straight to 1b.

### 1b. Tenant-scoped semantic search

Fallback and supplement. This is the canonical hybrid SQL but only the semantic CTE:

```sql
SELECT id, 1 - (embedding <=> $1::vector) AS sem_score
FROM memory_record
WHERE organization_id = $2 AND user_id = $3
  AND valid_to IS NULL AND is_archived = false
  AND memory_state IN ('active', 'warm')
  AND ($4::text[] IS NULL OR memory_type = ANY($4))
  AND ($5::text[] IS NULL OR tags && $5)
ORDER BY embedding <=> $1::vector
LIMIT 200;
```

### 1c. Keyword search

```sql
SELECT id, ts_rank_cd(search_vector, query) AS kw_score
FROM memory_record, plainto_tsquery('english', $1) query
WHERE organization_id = $2 AND user_id = $3
  AND valid_to IS NULL AND is_archived = false
  AND memory_state IN ('active', 'warm')
  AND search_vector @@ query
ORDER BY kw_score DESC
LIMIT 100;
```

### 1d. Graph-seeded retrieval

If `seed_entity_ids` is non-empty, traverse the entity graph up to `graph_depth` hops (default 1) and pull all linked memories:

```sql
WITH RECURSIVE walk AS (
  SELECT id AS entity_id, 0 AS depth
  FROM entity WHERE id = ANY($1) AND organization_id = $2
  UNION ALL
  SELECT CASE WHEN e.source_entity_id = w.entity_id
              THEN e.target_entity_id
              ELSE e.source_entity_id END,
         w.depth + 1
  FROM walk w JOIN entity_edge e
    ON (e.source_entity_id = w.entity_id OR e.target_entity_id = w.entity_id)
  WHERE w.depth < $3 AND e.organization_id = $2
)
SELECT DISTINCT mel.memory_id AS id, 1.0 AS graph_score
FROM walk w
JOIN memory_entity_link mel ON mel.entity_id = w.entity_id
WHERE mel.organization_id = $2;
```

The `walk` CTE is bounded by `depth < $3` so it terminates regardless of graph density.

### Merge

Union the four result sets, dedupe by `memory_id`. Each candidate carries up to four partial scores (semantic, keyword, graph) plus a flag for which source(s) found it. This information feeds Stage 2.

Total candidate set size: 200-400 typically.


## Stage 2 — Hybrid scoring

We combine signals using Reciprocal Rank Fusion (RRF) plus weighted metric scores. RRF is robust against differing score distributions across the four sources:

```
RRF(memory_id) = Σ 1 / (k + rank_in_source)   for each source it appeared in
                  k = 60
```

Then we mix with absolute metric scores from the memory record:

```
final_score = 
    0.40 × semantic_score
  + 0.25 × graph_score
  + 0.20 × importance       (from memory_record.importance, [0,1])
  + 0.10 × recency_score    (exp(-ln 2 × age_days / 30))
  + 0.05 × keyword_score
  + 0.10 × same_cluster_bonus
  - 0.30 × is_cold
  - 0.50 × is_archived (if not include_archived)
```

Where:

- `semantic_score`, `graph_score`, `keyword_score` are normalized to [0,1]. If a source did not return the memory, its score is the RRF-imputed estimate.
- `same_cluster_bonus` = 1 if the memory is in the matched cluster from Stage 1a, else 0.
- `is_cold` = 1 if memory_state == 'cold', else 0.

Cap final_score to [-1, 2] then truncate to top 50.

The Go data plane runs this entirely in memory (no DB round trip after Stage 1) since the candidate set is small.

## Stage 3 — Diversification

Top 50 from Stage 2 is fed through Maximal Marginal Relevance (MMR):

```
selected = []
remaining = candidates
while len(selected) < query.limit and remaining:
    best = argmax over remaining of:
        λ × score(c) - (1-λ) × max(cosine(c.emb, s.emb) for s in selected)
    selected.append(best)
    remaining.remove(best)
```

`λ = 0.7` balances relevance against diversity. This prevents the top results from being five rephrasings of the same fact.

After MMR, apply caps:
- Max 3 memories per entity (no entity dominates the result).
- Max 8 memories per `memory_type` (forces type variety in the top-K).

Truncate to `query.limit` (default 20).

## Stage 4 — Optional LLM rerank

When `rerank=true`:

```
prompt = """
Query: {query_text}

Memories:
1. {title}: {content_snippet}
2. {title}: {content_snippet}
...
50. ...

Rank these by relevance to the query. Return JSON: {"order": [memory_indexes]}
"""
```

Send to gpt-4o-mini (or Anthropic Haiku, configurable). On response, reorder; truncate to limit.

Failure modes:
- LLM timeout (>3s): return Stage 3 ordering, log warning.
- LLM returns bad JSON: same fallback.
- LLM returns indexes not in candidate set: same fallback.

Rerank is a per-request opt-in. Customers turn it on for high-stakes retrieval (e.g., the final context fetch before a billed LLM call), keep it off for casual retrieval.


## Performance targets

| Operation | Target p50 | Target p99 | Notes |
|---|---|---|---|
| Stage 0 (query understanding) | 5 ms | 60 ms | embed cache hit p50, miss p99 |
| Stage 1 (candidate generation) | 15 ms | 80 ms | parallel SQL, 1M memories tenant |
| Stage 2 (hybrid scoring) | 1 ms | 5 ms | in-memory math |
| Stage 3 (diversification) | 1 ms | 3 ms | in-memory math |
| Stage 4 (rerank, opt-in) | 400 ms | 700 ms | LLM bound |
| **Total without rerank** | **22 ms** | **150 ms** | |
| **Total with rerank** | **420 ms** | **850 ms** | |

These numbers are for an AX52 primary with HEL1 replica handling reads. We benchmark continuously in CI against a 1M memory fixture per tenant.

## Accuracy targets

We measure retrieval quality via the Dream Cycle's synthetic question evaluator (which becomes a CI fixture, not just a runtime feature):

| Metric | Target |
|---|---|
| Recall@10 | ≥ 0.85 |
| Recall@20 | ≥ 0.92 |
| MRR (Mean Reciprocal Rank) | ≥ 0.55 |
| nDCG@10 | ≥ 0.70 |

We freeze a public benchmark suite and report numbers in docs. CI fails if any metric regresses by > 5% from the stable release baseline.

## Why this is fast

1. **No global cross-tenant scan.** Every CTE has `organization_id = $tenant` in the WHERE.
2. **HNSW + B-tree composite indexes.** The tenant filter narrows before vector ANN search.
3. **Cluster routing.** The vector ANN runs over thousands of memories, not millions.
4. **Parallel candidate generation.** Four CTEs run concurrently in Postgres, results joined in memory.
5. **Replica reads.** Hot reads do not contend with writes.
6. **No HTTP hop.** Go calls Postgres directly. Python calls happen only when the customer explicitly reranks.
7. **Embedding cache.** Repeated queries (common in agent loops) skip the embed call.
8. **Static HNSW params per partition.** Active partition uses m=32 ef_search=64; cold partition uses IVFFlat which is slower but cheap on RAM.

## Why this is accurate

1. **Cluster-first retrieval beats global ANN.** The cluster routing is a learned partition.
2. **RRF + weighted scoring.** Robust against signal scale mismatch.
3. **Graph expansion with bounded depth.** Surfaces related memories the user "obviously" wants without runaway recursion.
4. **MMR diversification.** Top-K is information-dense, not redundant.
5. **Cold penalty + archived exclusion.** Stale memories deprioritized automatically.
6. **Same-cluster bonus.** Reinforces cluster-first signal.
7. **Per-entity and per-type caps.** Prevents one popular entity from drowning out everything.
8. **Optional rerank.** Customer can buy precision when they need it.

## What we explicitly didn't do at v1

| Considered | Why deferred |
|---|---|
| Cross-encoder rerank locally (BGE-reranker-v2) | Adds GPU dependency. Use LLM rerank for v1. |
| Hierarchical clustering with multiple levels | Single-level clusters are sufficient until ~10k clusters per tenant. |
| Per-tenant fine-tuning of weights | Pricing tier complexity not worth it pre-PMF. Static weights work. |
| Personalized retrieval (user feedback affects ranking) | Already covered by `RetrievalFeedbackEngine`. Importance score absorbs the feedback signal. |
| Multi-query expansion (Q2D, Q2E) | Marginal improvement vs HyDE; defer to learn from telemetry. |
| Time-decay-aware HNSW (vector that includes time) | pgvector doesn't support it. We use scalar recency multiplier. |
| Multimodal embeddings | Customers don't request images yet. |
| GraphRAG-style global summary | Compression engine handles entity-scoped summaries; cluster-scoped global summary is later. |

## Continuous improvement

The retrieval team owns these dashboards:

- Daily: Recall@K against synthetic question suite per tenant tier.
- Daily: p99 latency per stage.
- Weekly: top 100 worst-scored retrievals (lowest agent feedback). These become test fixtures.
- Monthly: per-customer retrieval health summary auto-generated, pushed to customer Slack.

When a customer reports "retrieval feels off," we have:
1. Their request_id (in their dashboard).
2. The full retrieval trace (stage timings, candidate scores, why each was selected).
3. The retrieval feedback for that memory in the next 24 hours (signal: did the agent use it).

This is the explainability story carried through to retrieval, not just memory creation.
