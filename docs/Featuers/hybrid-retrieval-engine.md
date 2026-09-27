# Hybrid Retrieval Engine

Contexta's **Hybrid Retrieval Engine** uses independent dense, lexical, and graph channels, merges them with weighted Reciprocal Rank Fusion (RRF), optionally reranks a bounded pool, and excludes superseded records.

---

## 1. Canonical Retrieval Flow

```text
Query and tenant/user filters
             |
             +-------------------+-------------------+
             |                   |                   |
             v                   v                   v
 Dense pgvector search   PostgreSQL lexical search   Entity graph
 cosine candidate       ts_rank_cd candidates        bounded traversal
             |                   |                   |
             +-------------------+-------------------+
                                 |
                                 v
                    Weighted Reciprocal Rank Fusion
                                 |
                                 v
                    Optional neural reranking
                        first 45 fused candidates
                                 |
                                 v
                     De-duplicate and top-K limit
                                 |
                                 v
                    Best-effort access-time touch
```

The canonical ordering is channel rank, not a pre-fusion weighted sum of semantic, graph, and importance signals. Component scores remain available as diagnostics, while RRF determines the fused order unless a configured reranker replaces that order.

---

## 2. Candidate Generation

The engine requests `max(query.limit * 15, 150)` candidates per channel. Repository methods may return fewer records, and every returned record is filtered again in memory.

### Channel 1: Dense Vector Similarity

- Uses the configured embedding vector and pgvector cosine ordering.
- Production deployments use the HNSW index defined on `memory_record.embedding`.
- Falls back to in-process cosine scoring when a repository does not expose vector search.

### Channel 2: Lexical Ranking

- Uses parameterized `websearch_to_tsquery('english', query_text)`.
- Orders matches by PostgreSQL `ts_rank_cd`, then recency and stable ID.
- Preserves exact tokens, identifiers, acronyms, and phrases that dense retrieval can miss.
- This is PostgreSQL full-text rank, not a claim of native BM25 scoring.

### Channel 3: Knowledge Graph

Graph seeds can be supplied explicitly or resolved from known entity names and aliases in the query. Top dense and lexical anchors can also contribute entities for a second bounded expansion. Traversal visits linked memories with inverse-degree weighting and depth decay, then hydrates graph-only records through the memory repository.

The default `RetrievalQuery.graph_depth` is 2. The schema accepts values through 5; the `retrieval_graph_max_hops` deployment setting is not enforced by the query schema itself. Optional Cortex graph routing can raise effective traversal to at least 3 hops.

---

## 3. Weighted Reciprocal Rank Fusion

For each memory, the canonical score is:

```text
RRF(memory) = sum(weight(channel) / (60 + rank(channel, memory)))
```

Default channel weights are:

| Channel | Weight |
| --- | ---: |
| Dense | 0.5 |
| Lexical | 0.3 |
| Graph | 0.2 |

Each channel de-duplicates repeated memory IDs before assigning ranks. Scores are normalized against the maximum possible active-channel score and capped at 1. Utility is added only as a small prior with weight 0.005, so it cannot dominate cross-channel agreement.

When optional Cortex routing is enabled and supplied to the engine, it adjusts channel weights for exact, semantic, or graph intent. A disabled or omitted Cortex preserves the defaults; the engine itself does not infer engine mode.

---

## 4. Reranking and Final Selection

When a reranker is configured, it receives at most the first 45 fused candidates. A successful reranker result becomes the final order; a missing or failed reranker preserves the RRF order. The engine then de-duplicates by memory ID and applies the query limit.

The reranker is bounded on purpose: large candidate pools increase model latency and memory use without giving the reranker enough extra context to justify the cost.

---

## 5. Truth and Tenant Filters

Every channel excludes a record when:

- `organization_id` or `user_id` does not match the query
- `valid_to` is set, meaning the record is superseded
- Archived records are excluded by default
- Cold records are excluded when `include_cold` is false
- Memory-type or tag filters do not match

These checks run both in the repositories and in the engine's final inclusion guard.

---

## 6. Read-Age Updates

Every final result triggers a best-effort `last_accessed_at` update. The repository bulk path updates all returned IDs in one tenant-scoped statement; a compatibility fallback may update records individually. Read age is separate from `created_at`, `event_at`, and `observed_at`.

A touch failure does not discard an otherwise successful retrieval result, so availability takes precedence over decay bookkeeping.

---

## 7. Validated Gate

The focused tests verify independent dense/lexical candidates, graph-only hydration, cross-channel RRF behavior, bounded utility influence, parameterized lexical SQL, and the 45-record reranker cap:

```bash
uv run pytest tests/test_retrieval_fusion.py tests/test_retrieval_engine.py -q
```

These tests validate mechanics, not benchmark accuracy. Current LoCoMo limitations are documented in [Quality Gates & Benchmark Evidence](quality-gates.md).
