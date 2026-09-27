# Automated Tasks & Dream Cycles

Contexta uses Celery and Redis for extraction, embedding, durable-outbox leases, and periodic memory maintenance. Queue routing and task acknowledgement settings bound work independently so one slow stage does not consume every worker slot.

---

## 1. Worker Architecture

```text
Celery Beat
    |
    +-- outbox dispatch every 5 seconds
    +-- decay every 24 hours
    +-- reflection every 24 hours
    +-- dream every 7 days

Task producers
    |
    +-- extraction queue
    +-- embedding queue
    +-- outbox queue
    +-- maintenance queue
```

Celery uses Redis as broker and result backend. The application enables UTC and JSON serialization.

---

## 2. Queue Routing

| Queue | Tasks | Workload |
| --- | --- | --- |
| `extraction` | `process_observation`, `process_observation_outbox` | Durable and legacy extraction, deduplication, graph persistence |
| `embedding` | `generate_memory_embedding`, `generate_memory_embeddings` | Single or bounded-batch vector generation and storage |
| `outbox` | `claim_outbox_events`, `dispatch_outbox` | Batched, leased outbox claims |
| `maintenance` | decay, reflection, dream | Periodic background maintenance |

Extraction and embedding tasks retry up to three times with a 60-second default delay. Durable observation processing also uses a 300-second lease and records at most three attempts. A durable failure sets `next_attempt_at` 60 seconds later; a functioning dispatcher must claim that retry. Dream tasks currently allow one retry.

---

## 3. Backpressure and Delivery Semantics

The Celery application uses:

- `task_acks_late = true`
- `task_reject_on_worker_lost = true`
- `worker_prefetch_multiplier = 1`

Late acknowledgement keeps a task unacknowledged until execution completes. Rejecting work when a worker is lost allows the broker to redeliver it. A prefetch multiplier of one limits each worker process from hoarding queued tasks while another process is idle.

These settings improve load spreading, but they are not complete admission control. Operators still need broker memory alerts, queue-depth monitoring, payload-size limits, and capacity planning for the model server.

The embedding worker accepts either one memory ID or a sequence. Batch work is split into chunks of 32 by default and embeds each chunk with a concurrency semaphore of four; these values are configurable through `CONTEXTA_EMBEDDING_TASK_BATCH_SIZE` and `CONTEXTA_EMBEDDING_TASK_CONCURRENCY`. The current fast orchestrator still submits individual IDs.

There is no second Go ingress path. The Go layer is a stateless TLS edge (`:8443`) that verifies API keys, applies rate limits, and reverse proxies to the Python API, so every observation reaches the same `ingestion_observation` ledger and the same outbox. The former Go staging table and its `drain_go_staging` task have been removed.

---

## 4. Durable Outbox Dispatch

`IngestionOutboxRepository.claim_pending()` provides the database-side backpressure primitive:

- Default claim size: 100 events
- Repository hard cap: 1,000 events per claim
- Default lease: 300 seconds
- Ordering: oldest `created_at` first
- Concurrency: PostgreSQL `FOR UPDATE SKIP LOCKED`
- Recovery: expired claims become eligible again
- Terminal state: optional maximum attempts move events to `dead_letter`

A successful relay must retain the returned lease token, publish the event downstream, and call `mark_outbox_published` only after acknowledgement. Failed publication should call the retry method with an availability time.

### Outbox Recovery

The public route's normal path is durable: it commits the observation and outbox event, then schedules `process_observation_outbox` by identifiers on the `extraction` queue. The task claims both the observation and its outbox event, runs the orchestrator, completes or dead-letters the attempt, and marks the event published only after the durable observation commit.

Periodic recovery now discovers pending organizations, claims bounded batches with `FOR UPDATE SKIP LOCKED`, and publishes one identifier-only extraction task per event. The stock worker consumes the `outbox` queue, and the beat schedule runs the tenant-aware dispatcher.

Broker-level crash tests and deployment-specific queue-depth alerts remain operational validation work. See [Temporal Grounding & Durable Ingestion](temporal-grounding-and-durable-ingestion.md).

---

## 5. Dream Cycles

`DreamCycleEngine` and `contexta/workers/dream_tasks.py` periodically examine memory and entity coverage. Current behavior can generate synthetic questions, retrieve answers, identify missing-memory candidates, and persist a `DreamRecord` summary.

Consolidation should preserve original evidence. Synthesized or archived records must not erase source memories or bypass tenant-scoped repositories.

---

## 6. Decay and Reflection

The decay worker transitions unpinned memories according to configured day thresholds. Pinned records are exempt. Successful retrieval updates `last_accessed_at`, so decay follows read age rather than only write age.

The reflection worker runs daily. Reflection output remains subject to the same extraction, secret filtering, truth maintenance, tenant scoping, and audit rules as direct observations.

---

## 7. Model Server

The local model server listens on `:8001` and hosts:

- `Qwen/Qwen3-Embedding-0.6B` with 1024-dimensional output
- `Qwen/Qwen3-Reranker-0.6B`

It provides embedding, reranking, and classification endpoints. Latency depends on hardware, model load, batch shape, and concurrent requests; no fixed sub-15ms latency is claimed by this documentation.

---

## 8. Validated Gate

Durable claim behavior is covered by:

```bash
uv run pytest tests/test_ingestion_outbox.py -q
```

The test validates migration linkage, tenant-scoped idempotency metadata, PostgreSQL `SKIP LOCKED`, expired-lease recovery, and task-safe result payloads. Broker crash-recovery and deployment soak tests remain operational validation work.
