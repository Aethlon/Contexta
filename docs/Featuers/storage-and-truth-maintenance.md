# Storage & Truth Maintenance

Contexta stores memory as versioned relational records with explicit temporal provenance, vector and lexical indexes, and graph links. Superseded content remains auditable but is excluded from active retrieval.

---

## 1. Memory Storage

The core table is `memory_record`, mapped by `contexta/models/memory.py` and created in the initial Alembic migration.

### Identity and Content

| Field | Role |
| --- | --- |
| `id` | Stable memory identifier |
| `organization_id` | Mandatory tenant boundary |
| `user_id` | Subject boundary within the tenant |
| `session_id` | Optional source conversation |
| `memory_type` / `source_type` | Classification and provenance type |
| `title` / `content` | Retrieval text |
| `structured_data` / `tags` | Parsed attributes and labels |
| `embedding` | pgvector representation |
| `search_vector` | Trigger-maintained PostgreSQL full-text vector |

Repositories scope business queries by `organization_id`; retrieval additionally checks `user_id`.

### Scores and Lifecycle

| Field | Meaning |
| --- | --- |
| `confidence` | Source credibility baseline |
| `importance` | Durable relevance signal |
| `utility_score` | Feedback-adjusted utility prior |
| `memory_state` | Active, warm, cold, or archived lifecycle state |
| `is_pinned` | Exemption from decay |
| `is_archived` | Soft exclusion from default retrieval |
| `last_accessed_at` | Read-age touch after successful recall |

---

## 2. Temporal Provenance

Migration `007` adds:

- `event_at`
- `observed_at`
- `temporal_precision`
- `temporal_basis`
- `fact_key`
- `lineage_id`
- `source_id`
- `source_message_id`

`event_at` and `observed_at` are timezone-aware timestamps. `event_at` describes when the remembered event happened; `observed_at` records when Contexta observed the source. Relative source expressions can be resolved before extraction and then retained as normalized text plus structured match metadata.

The original expression, resolved expression or interval, precision, timezone, and basis prevent an inferred date from looking indistinguishable from an explicit source date. If no source reference exists, `event_at` remains empty and the basis is `ingestion_fallback`.

### Time Separation

| Clock | Fields | Purpose |
| --- | --- | --- |
| Event time | `event_at` | When the described event happened |
| Observation time | `observed_at` | When the source was observed |
| Truth interval | `valid_from`, `valid_to` | Which record is current truth |
| Storage time | `created_at`, `updated_at` | Database lifecycle |
| Read time | `last_accessed_at` | Decay and feedback age |

`valid_from` is derived from `event_at`, then `observed_at`, then ingestion time. `valid_to = NULL` means the record is current.

`event_at` and `observed_at` are timezone-aware, while the pre-existing truth, storage, and read-age columns are timezone-naive and treated as UTC by current code. A timezone-aware lifecycle-column migration remains a separate consistency task.

---

## 3. Indexes

| Index | Purpose |
| --- | --- |
| `ix_memory_record_embedding_hnsw` | pgvector cosine candidate generation |
| `ix_memory_record_search_vector_gin` | PostgreSQL full-text lookup |
| `ix_memory_record_org_valid_to_partial` | Current-truth filtering |
| `ix_memory_record_org_user_type` | Tenant/user/type access |
| `ix_memory_record_org_user_state` | Lifecycle queries |
| `ix_memory_record_org_user_event` | Event-time access |
| `ix_memory_record_org_fact_key` | Provenance lookup |

`memory_record` carries **two** vector columns, added by revision `012`:

| Column | Width | Profile | HNSW index |
| :--- | ---: | :--- | :--- |
| `embedding_1024` | `vector(1024)` | `offline-qwen3-1024` — the default | `ix_memory_record_embedding_1024_hnsw` |
| `embedding` | `vector(1536)` | `online-openai-1536` | `ix_memory_record_embedding_hnsw` |

A row carries the profile, model, version, and dimensions it was embedded under (`embedding_profile`, `embedding_model`, `embedding_version`, `embedding_dimensions`), with a CHECK constraint limiting `embedding_dimensions` to 1024 or 1536. The two profiles are **never** mixed: vectors are not padded or truncated, and a row that has a vector in the other profile's column is skipped rather than coerced. If you switch profiles, re-embed — a column width is not something a config change can alter.

---

## 4. Truth Maintenance

When a new record is likely to contradict a current record, truth maintenance:

1. Reads current truths for the same tenant-scoped user and memory type.
2. Applies a conservative contradiction check based on title similarity and changed content.
3. Creates a `memory_version` row linking the old record to `superseded_by_id`.
4. Sets the old record's `valid_to`.
5. Writes an audit event.
6. Leaves the old content and lineage in storage.

```text
T0: "User uses Python 3.9"   valid_from=T0, valid_to=NULL
T1: "User uses Python 3.12"  valid_from=T1, valid_to=NULL
                              old valid_to=T1
```

Dense, lexical, and graph retrieval require `valid_to IS NULL`, and the retrieval engine repeats the truth filter as a final guard.

`fact_key` and `lineage_id` provide provenance metadata. An explicit fact key remains stable across updates; the current fallback includes title and content and can change with the fact value. The contradiction detector does not use either field as its primary key, so semantic fact-key contradiction resolution is not complete.

---

## 5. Durable Ingestion Tables

Migration `006` separately stores accepted source input before memory derivation:

- `ingestion_observation`
- `ingestion_source_turn`
- `ingestion_attempt`
- `ingestion_dead_letter`
- `ingestion_outbox_event`

These tables provide tenant-scoped idempotency, payload hashes, source-turn replay checks, leases, attempt history, terminal failures, and outbox state. The public observation route commits the observation, source turns, and `observation.accepted` event before returning `202 Accepted`, then schedules identifier-only durable processing. Tenant-aware periodic recovery claims pending events, republishes identifier-only work, and converges published state after downstream processing; broker crash tests and deployment soak tests remain operational work.

See [Temporal Grounding & Durable Ingestion](temporal-grounding-and-durable-ingestion.md) for lifecycle and integration details.

---

## 6. Knowledge Graph Storage

- `entity` stores canonical names, aliases, types, and aggregate attributes.
- `entity_edge` stores weighted relationships between entities.
- `memory_entity_link` connects memories to the entities mentioned in them.
- `audit_log` records operational and supersession actions.
- `memory_version` records superseded content and forward lineage.

Graph traversal supplies relationship context, while `MemoryVersion` and audit records carry supersession history; truth maintenance intentionally does not create zero-information entity self-edges for supersession.
