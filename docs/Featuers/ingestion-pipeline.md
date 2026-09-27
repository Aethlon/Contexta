# Ingestion Pipeline Deep Dive

The **Contexta Ingestion Pipeline** transforms raw conversational streams, tool interactions, and system events into sanitized, temporally grounded, typed, deduplicated, and graph-connected durable memories.

---

## 1. Pipeline Lifecycle Overview

```text
Observation Payload
         |
         v
Sensitive Data Filter ---> Secret redaction ([REDACTED])
         |
         v
Temporal Normalizer ---> Reference time, timezone, expression matches
         |
         v
Extraction Worker ---> Typed memory candidates
         |
         v
Secondary Filter ---> Discard candidates containing credentials
         |
         v
Memory Deduplicator ---> Discard / merge / novel
         |
         v
Memory Scoring Engine ---> Importance and confidence
         |
         v
Bulk Entity Resolver ---> Canonical entities, links, graph edges
         |
         v
Truth Maintenance ---> Supersession and lineage
         |
         v
Caller-owned SQL transaction ---> Atomic records, links, and edges
         |
         v
Embedding queue ---> Asynchronous vector generation
```

The current production orchestrator uses `session.flush()` inside the caller's transaction. The Celery extraction task owns and commits that transaction; a direct caller must commit or roll back it explicitly.

---

## 2. Ingress and Durability Boundaries

### Public HTTP Path

`POST /v1/observations` now performs the durable acceptance boundary:

1. Validate required tenant, user, session, and message fields.
2. Reject an authenticated organization that conflicts with the request body or header.
3. Redact secrets from a deep copy of the payload.
4. Idempotently insert `ingestion_observation` and ordered `ingestion_source_turn` rows.
5. Insert one `observation.accepted` outbox row with a tenant-scoped unique event key.
6. Commit before returning `202 Accepted` with durable identifiers.
7. Schedule `process_observation_outbox` with identifiers only; no secret-bearing payload is placed in the task arguments.
8. Expose tenant-scoped status through `GET /v1/observations/{observation_id}` and status aliases.

The durable worker uses a 300-second observation lease and a maximum of three attempts. A failure records a 60-second `next_attempt_at`; a dispatcher must claim that retry later. Completion clears the lease and marks the observation complete. Exhausted attempts move the observation to dead-letter state and retain error details.

There is no separate Go high-volume path. The Go layer is a stateless TLS edge that reverse proxies to the Python API, so every observation enters through the same route, the same redaction scan, and the same outbox. The former Go staging table and its drain task have been removed.

### Outbox Recovery Boundary

Normal HTTP processing is scheduled after durable commit. Periodic recovery discovers pending organizations, claims bounded batches with `FOR UPDATE SKIP LOCKED`, and publishes one identifier-only processor per event. The worker consumes the `outbox` queue, and identifier-only processing claims the corresponding event before marking it published.

Acknowledged input is therefore recoverable after a worker or broker restart. Deployment-specific broker crash tests, queue-depth alerts, and soak validation remain operational work. See [Temporal Grounding & Durable Ingestion](temporal-grounding-and-durable-ingestion.md).

---

## 3. Temporal Grounding

`ObservationPayload` accepts `occurred_at`, `observed_at`, `timezone`, `source_id`, and `message_id`, with per-message overrides. Before extraction, Contexta normalizes supported relative expressions against `occurred_at` first and `observed_at` second.

Examples include:

- `yesterday`, `today`, and `tomorrow`
- `last`, `this`, and `next` week, month, or year
- Number-word and numeric `N units ago` expressions
- Qualified and bare weekdays
- Explicit ISO dates

Relative dates are not invented when the source has no usable reference. The normalized message, original expression, resolved interval, precision, timezone, and source IDs accompany the extraction prompt. Extracted memories retain event time, observation time, temporal basis, provenance IDs, and a structured temporal block.

---

## 4. Primary and Secondary Sanitization

### Primary Filter

Implemented in `contexta/core/extraction/sensitive_filter.py`, the primary filter runs on raw messages before extraction. It detects and replaces:

- Passwords and one-time codes
- Luhn-valid payment cards
- AWS access keys
- GitHub personal access tokens
- OpenAI and Stripe-style keys
- JWTs and bearer tokens

The current HTTP route invokes the primary scan before Celery publication. It is the only ingestion path, so every observation is redacted by the same filter.

### Secondary Filter

`secondary_scan()` runs over every extracted memory. A candidate that still appears to contain a credential is discarded before deduplication, scoring, or storage.

---

## 5. Extraction and Optional Routing

`ExtractionWorker` builds a compact JSON extraction prompt from normalized messages, temporal metadata, source identifiers, and optional policy or Cortex guidance. It validates returned memories, normalizes entity references, applies conservative defaults, and performs the secondary secret scan.

Contexta Cortex is advisory. In offline mode the current fast orchestrator bypasses the default Cortex write call; feature-disabled and online configurations can provide routing hints. A Cortex early-skip decision can avoid an extraction call for a candidate classified as ephemeral.

---

## 6. Deduplication and Scoring

### Deduplication

1. Exact duplicates are discarded.
2. Semantic overlap above the merge threshold updates the existing record and schedules re-embedding.
3. Novel records proceed to scoring and persistence.

### Scoring

The importance engine combines memory type, entity signal, emphasis, and decision impact. Confidence starts from source type, including `user_explicit`, `agent_inference`, and `system_observed`. Final values are bounded before persistence.

---

## 7. Entity Resolution and Persistence

`BulkEntityResolver` batches entity lookup, normalizes canonical names and aliases, creates missing entities, links memories to entities, and updates co-occurrence edges. Memories, entities, links, and edges are staged in one caller-owned transaction.

Truth maintenance then invalidates contradicted current records by setting `valid_to`, writes `MemoryVersion` lineage, and emits audit data. Superseded records remain in storage but are excluded from active dense, lexical, graph, and reranked retrieval.

The orchestrator now records memory IDs for embedding and the task publishes them only after the caller commits its database transaction. Embedding updates remain idempotent, and extraction and embedding tasks use late acknowledgement, reject work when a worker is lost, and retry transient failures with bounded backoff. The embedding worker supports bounded batches of up to 32 with configurable concurrency.

---

## 8. Operational Limits

- Maximum observation body: 1 MiB by default
- Extraction retry limit: 3
- Embedding retry limit: 3
- Celery prefetch multiplier: 1
- Queue routing: `extraction`, `embedding`, `maintenance`, plus a separately routed `outbox`

These controls bound in-process work, but they are not a complete admission-control system. Queue-depth alerts, broker capacity, and crash/soak tests remain deployment responsibilities.
