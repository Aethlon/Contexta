# Hybrid Memory Layer Architecture

Contexta stores each memory in relational metadata, dense vector space, PostgreSQL full-text search, and the entity graph. Retrieval treats dense, lexical, and graph results as independent candidate channels and combines their ranks with weighted RRF.

---

## 1. Tri-Modal Representation

```text
                       Canonical MemoryRecord
                                |
          +---------------------+---------------------+
          |                     |                     |
          v                     v                     v
   pgvector embedding   TSVECTOR + GIN         Entity links and edges
   cosine/HNSW          ts_rank_cd             bounded traversal
```

- **Dense vectors** provide semantic similarity and fuzzy conceptual matching.
- **PostgreSQL full-text search** provides deterministic token and identifier matching.
- **Entity relationships** connect memories that share people, projects, places, tools, or concepts.

These representations complement one another. A vector-only design is weak on exact codes, lexical-only search is weak on paraphrase, and graph-only recall depends on extraction quality.

---

## 2. Memory Record

`contexta/models/memory.py` stores:

- Tenant identity: `organization_id` and `user_id`
- Conversation identity: `session_id`
- Classification: `memory_type` and `source_type`
- Content: `title`, `content`, `structured_data`, and `tags`
- Intelligence: `confidence`, `importance`, and `utility_score`
- Truth lifecycle: `valid_from`, `valid_to`, and `memory_state`
- Temporal provenance: `event_at`, `observed_at`, `temporal_precision`, and `temporal_basis`
- Source lineage: `fact_key`, `lineage_id`, `source_id`, and `source_message_id`
- Retrieval state: `embedding`, `search_vector`, and `last_accessed_at`
- Storage lifecycle: `is_pinned`, `is_archived`, `created_at`, and `updated_at`

`event_at` and `observed_at` use timezone-aware columns. Existing lifecycle and access timestamps remain timezone-naive UTC columns. See [Storage & Truth Maintenance](storage-and-truth-maintenance.md) for the full time model.

### Vector Dimension Caveat

`memory_record` has two vector columns, not one: `embedding_1024` (`vector(1024)`, the offline `offline-qwen3-1024` default) and `embedding` (`vector(1536)`, the online `online-openai-1536` profile), each with its own HNSW index. Revision `012` added the 1024 column specifically so the offline default stopped fighting the schema.

The two profiles are never mixed. `active_embedding` returns the 1024 column if it is populated and falls back to the 1536 one; retrieval skips a row whose vector lives in the *other* profile's column rather than padding or truncating it, and `embedding_dimensions` is CHECK-constrained to 1024 or 1536. A deployment must therefore use a persisted width that matches its embedding provider, or re-embed after switching.

The LoCoMo harness zero-pads to 1536. That is a benchmark-harness accommodation, not a production behaviour, and no number in this repository was produced by mixing profiles.

---

## 3. Retrieval Execution Flow

### Candidate Generation

1. Dense search returns cosine-ordered vector candidates.
2. Lexical search returns `ts_rank_cd` candidates using a parameterized web-search query.
3. Graph traversal returns memories associated with explicit or inferred entity seeds.
4. Each channel is independently bounded and de-duplicated.

### Canonical Fusion

```text
RRF(memory) = sum(channel_weight / (60 + channel_rank))
```

Default weights are 0.5 dense, 0.3 lexical, and 0.2 graph. A small 0.005 utility prior is applied after rank fusion. Cross-channel agreement therefore matters more than any single stored score.

### Reranking and Finalization

An optional cross-encoder receives at most 45 fused candidates. The engine de-duplicates final results, applies the requested limit, and updates `last_accessed_at` for returned records.

The engine does not currently perform MMR diversification or cluster-first search. Documentation must not describe those as part of the canonical path.

---

## 4. Truth and Retrieval

Dense and lexical repository queries require `valid_to IS NULL`. The engine repeats tenant, user, truth, archive, cold-state, type, and tag checks after retrieval. Superseded records remain available for lineage and audit but do not enter active recall.

Truth maintenance is conservative: it compares current records of the same memory type and uses high title similarity plus changed content as a likely contradiction. `fact_key` and `lineage_id` are persisted provenance, not the engine's contradiction key; fallback keys can also change when title or content changes.

---

## 5. Layer Summary

| Layer | Technology | Function |
| --- | --- | --- |
| Memory truth | Relational `valid_from` / `valid_to` | Current-fact filtering and supersession history |
| Dense retrieval | pgvector cosine/HNSW | Semantic candidate generation |
| Lexical retrieval | PostgreSQL `TSVECTOR` + GIN | Exact-token and phrase candidate generation |
| Graph retrieval | Entity links and edges | Relationship-aware expansion |
| Fusion | Weighted RRF, `k = 60` | Cross-channel rank agreement |
| Reranking | Bounded cross-encoder | Final precision ordering |
| Read age | `last_accessed_at` | Decay based on successful recall |

See [Hybrid Retrieval Engine](hybrid-retrieval-engine.md) for formulas, filters, and validated behavior.
