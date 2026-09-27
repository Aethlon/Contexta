# Temporal Grounding & Durable Ingestion

Contexta now has two foundations for long-running memory: explicit temporal provenance for extracted facts and a tenant-scoped ingestion ledger with leases, attempts, dead letters, and an outbox. These foundations preserve late or replayed input, but their current API integration boundary is described below.

---

## 1. Temporal Contract

### Observation Timestamps

| Field | Meaning | Role in grounding |
| --- | --- | --- |
| `occurred_at` | When the source event happened | Preferred reference for relative expressions |
| `observed_at` | When Contexta or the source observed the event | Fallback reference and receipt provenance |
| `timezone` | IANA timezone for source-local dates | Controls day, weekday, and calendar-boundary resolution |

A message can override payload-level timestamps and timezone. The core `ObservationPayload` contract supports these fields, but the current Python and TypeScript SDK `observe()` method signatures do not expose them yet. SDK callers must use the REST contract directly or wait for an SDK update.

Reference selection is:

1. Message `occurred_at`
2. Message `observed_at`
3. Payload `occurred_at`
4. Payload `observed_at`

Timezone selection is message timezone, payload timezone, timezone carried by the selected timestamp, then UTC.

```json
{
  "user_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "organization_id": "00000000-0000-0000-0000-000000000001",
  "session_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
  "occurred_at": "2026-09-07T12:00:00-04:00",
  "observed_at": "2026-09-07T12:01:05Z",
  "timezone": "America/New_York",
  "source_id": "conversation-42",
  "message_id": "message-7",
  "messages": [
    {
      "role": "user",
      "content": "The release happened yesterday."
    }
  ]
}
```

This example resolves `yesterday` to `2026-09-06` in `America/New_York` while preserving the source expression in temporal match metadata.

### Supported Relative Expressions

- `yesterday`, `today`, and `tomorrow`
- `last`, `this`, and `next` week, month, or year
- `last`, `this`, and `next` weekday
- Number-word or numeric `N days/weeks/months/years ago`
- Bare weekday names
- Explicit ISO dates

Contexta does not invent a date for a relative expression when no usable reference time exists. The expression remains unchanged, `event_at` stays empty, and the temporal basis is `ingestion_fallback`.

### Memory Provenance

Extraction and persistence retain:

- `event_at`: absolute time of the event described by the memory
- `observed_at`: observation receipt time, defaulting to ingestion time when absent
- `temporal_precision`: precision such as `day`, `week`, `month`, `year`, `exact`, or `unknown`
- `temporal_basis`: provenance such as `relative_expression`, `explicit_date`, `extracted_event_at`, payload basis, or `ingestion_fallback`
- `source_id` and `source_message_id`
- `fact_key` and `lineage_id`
- A `structured_data.temporal` block and any resolved `temporal_expressions`

`fact_key` and `lineage_id` provide provenance metadata. An explicit `fact_key` is stable across updates; the current fallback derives it from tenant, user, type, entities, title, and content, so a changed value can produce a different key. The truth engine still selects contradiction candidates by tenant, user, memory type, and conservative title similarity rather than by `fact_key`.

---

## 2. Storage-Time Semantics

Contexta keeps source time, truth time, storage time, and read time separate:

| Concept | Field | Meaning |
| --- | --- | --- |
| Event time | `event_at` | When the remembered event happened |
| Observation time | `observed_at` | When Contexta received or observed the source |
| Truth start | `valid_from` | Start of the record's active truth interval |
| Truth end | `valid_to` | End of the active truth interval; `NULL` means current |
| Storage time | `created_at` / `updated_at` | Database record lifecycle |
| Read age | `last_accessed_at` | Last successful retrieval touch used by decay |

For a new memory, `valid_from` is derived from `event_at`, then `observed_at`, then ingestion time. This is not a replacement for the explicit event and observation fields: it supports the existing truth and lifecycle schema.

`event_at` and `observed_at` use timezone-aware PostgreSQL timestamps. The pre-existing `valid_from`, `valid_to`, `created_at`, `updated_at`, and `last_accessed_at` columns remain timezone-naive and are treated as UTC by the current persistence code. A future migration to timezone-aware lifecycle columns would remove that convention.

---

## 3. Durable Ingestion Ledger

Migration `006` adds five tenant-scoped tables:

| Table | Responsibility |
| --- | --- |
| `ingestion_observation` | Canonical payload, SHA-256 request hash, idempotency key, status, and lease |
| `ingestion_source_turn` | Ordered source messages with stable turn indexes and optional source IDs |
| `ingestion_attempt` | Attempt number, worker, lease, timing, and failure details |
| `ingestion_dead_letter` | Terminal observation failure retained for inspection or replay |
| `ingestion_outbox_event` | Deduplicated event, availability time, lease, publish attempt, and terminal state |

Idempotency is unique per `(organization_id, idempotency_key)`. Replaying identical content returns the existing observation; reusing a key with a different payload hash raises an idempotency conflict. Every repository read, claim, retry, and completion operation remains tenant-scoped.

### Attempt Lifecycle

```text
pending -> processing -> completed
                    \-> retrying -> processing
                    \-> dead_letter
```

Claims use `FOR UPDATE SKIP LOCKED` on PostgreSQL, allowing multiple consumers without claiming the same row. Each claim receives a worker ID, random lease token, and expiry. An expired processing claim becomes eligible for recovery. Completion and failure updates can verify both worker and lease token, preventing a stale worker from overwriting a newer attempt.

### Outbox Lifecycle

```text
pending -> claimed -> published
                  \-> failed -> claimed
                  \-> dead_letter
```

The outbox has a unique `(organization_id, event_key)`. Claiming is ordered by creation time, bounded by a requested limit, and uses the same row-lock and lease model. Repository defaults are 100 events per claim and a 300-second lease. Callers may provide a maximum-attempt count; exhausted events move to `dead_letter`.

The durable transaction boundary commits the observation and its outbox event together. A separate relay claims the event, publishes identifier-only work, and marks it published only after the durable extraction attempt completes successfully.

---

## 4. Current Integration Boundary

The durable ledger is now part of the public observation path:

1. `POST /v1/observations` validates tenant and payload fields and runs primary secret redaction.
2. A savepoint-backed repository operation idempotently inserts the observation and ordered source turns, then inserts `observation.accepted` into the outbox.
3. The request-scoped database dependency commits before the endpoint returns `202 Accepted` with both `job_id` and `observation_id`.
4. A FastAPI background task publishes `process_observation_outbox` by durable identifiers. Processing claims the observation with a 300-second lease and allows at most three attempts. A failure records a 60-second `next_attempt_at`; a dispatcher must claim that retry later.
5. `GET /v1/observations/{observation_id}` and its status aliases expose observation state, attempt count, outbox state, errors, and timestamps. The lookup is tenant-scoped.

Authentication middleware and route validation reject an authenticated organization that differs from the body or header organization. This prevents a valid API key from writing a durable observation into another tenant.

Periodic outbox recovery is implemented across the database, dispatcher, and worker: pending organizations are discovered, events are claimed with `FOR UPDATE SKIP LOCKED`, one identifier-only processor is published per event, and the event is claimed before published-state convergence. Deployment-specific broker crash tests, queue-depth alerts, and soak validation remain operational work. See [Automated Tasks & Dream Cycles](automated-tasks-and-dreaming.md) for queue details.

---

## 5. Validated Correctness Gate

The focused regression suite validates timezone-aware relative dates, refusal to invent missing dates, persisted temporal metadata, tenant-scoped idempotency, PostgreSQL `SKIP LOCKED`, expired-lease recovery, and safe outbox result metadata:

```bash
uv run pytest tests/test_temporal_normalization.py tests/test_ingestion_outbox.py -q
```

The checked working tree passed this gate on September 24, 2026. See [Quality Gates & Benchmark Evidence](quality-gates.md) for the full gate list and LoCoMo limitations.
