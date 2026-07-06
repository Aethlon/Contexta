# 16 — Error Handling and Failsafe

This document is the playbook for what happens when things go wrong: client-side errors, network drops, server-side failures, partial writes, LLM provider outages, and data integrity threats. Every scenario has a defined behavior; we never improvise during production incidents.

The customer's specific concern: *"the client sent data but we were unable to receive it."* That scenario, plus its cousins, is treated as first-class here.

## Decisions of record

1. **At-least-once delivery for writes, at-most-once visibility.** We never lose an observation that the SDK successfully POSTed. We may process it twice; idempotency keys prevent the duplicate from creating duplicate memories.
2. **Idempotency keys are mandatory on retried writes.** SDKs auto-generate them. Direct API users are strongly encouraged.
3. **Local SDK durable buffer.** When the network is down, the SDK buffers up to 1000 observations to disk and replays on reconnect.
4. **Server-side write-ahead at the gateway.** Before responding 202, the gateway writes the observation envelope to a Redis-backed durable queue. Even if the worker dies, the observation persists.
5. **Quota and rate limits return 429, not 500.** Customers know exactly why a request was rejected.
6. **All failures are visible.** Customers see them in the dashboard and via webhooks. We never hide a failure to make metrics look better.


## Failure scenarios and behaviors

### 1. Client → gateway network failure (request never arrives)

**Symptom:** SDK times out or sees connection refused.

**Behavior:**
- SDK retries with exponential backoff: 1s, 2s, 4s, 8s, 16s. Max 5 retries.
- After max retries, SDK appends to local durable buffer (`~/.contexta/buffer.jsonl` for CLI/server, IndexedDB for browser).
- Buffer size cap: 1000 observations or 50 MB, whichever first. Beyond that, oldest observations dropped (logged + customer dashboard alert).
- On next successful API call, SDK flushes buffer in batches of 50.
- Same idempotency key reused on each retry.

**Failure mode covered:** Network partition, customer agent crash mid-flight, brief contexta outage.

```python
# contexta_client/_http.py (illustration)
class DurableBuffer:
    def append(self, payload: dict) -> None:
        with self._lock:
            with open(self._path, "a") as f:
                f.write(json.dumps(payload) + "\n")
    
    def replay(self, client) -> int:
        replayed = 0
        for line in self._read_all():
            try:
                client._raw_post("/v1/observations", json.loads(line))
                replayed += 1
            except RetryableError:
                break  # stop, will retry next flush
            except FatalError:
                self._move_to_dead_letter(line)
        self._truncate(replayed)
        return replayed
```

### 2. Gateway → data plane network failure

**Symptom:** Gateway accepts request, internal call to data plane fails.

**Behavior:**
- Gateway has already written the observation envelope to Redis Stream `meter:events:writes` before forwarding.
- Gateway returns 202 to client with the `job_id`.
- Background worker reads the stream and retries the data plane call until success.
- Customer's request was acknowledged; they should not retry.

**Implementation:** Gateway writes to Redis BEFORE forwarding. Even if the gateway crashes after the client sees 202, the observation survives in Redis. A separate "write recovery" task processes the stream.

```
Client POST /v1/observations
       │
       ▼
Gateway → XADD writes:queue {payload, request_id, idempotency_key}  (durable, AOF)
       │
       ▼
Gateway → forward to data plane (best effort)
       │   ├─ success: ack the stream entry, return 202 to client
       │   ├─ timeout: return 202 to client (already durable in Redis), recovery worker handles
       │   └─ data plane error 5xx: same as timeout
       │
       ▼
Recovery worker XREADGROUP writes:queue → retries any unacked entries
```

### 3. Data plane crash mid-write

**Symptom:** Postgres INSERT partially executed.

**Behavior:**
- All writes wrapped in a single transaction. Postgres atomicity guarantees no partial row.
- Connection drop mid-transaction → Postgres aborts and rolls back.
- Data plane retries from the message in Redis Stream (not yet acked).
- Idempotency key on the table prevents double-insert if the original transaction succeeded but the ack was lost.

```sql
-- observation_envelope table has idempotency_key UNIQUE
INSERT INTO observation_envelope (id, idempotency_key, ...)
VALUES (...)
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING id;
```

If `RETURNING` is empty, the original write already succeeded; we ack the stream entry and move on.

### 4. Worker crash mid-extraction

**Symptom:** Celery task started but did not finish (LLM call mid-flight, OOM, machine reboot).

**Behavior:**
- Celery configured with `task_acks_late=True` and `task_reject_on_worker_lost=True`.
- A crashed task returns to the queue and is picked up by another worker.
- Extraction is internally split into checkpoints: redaction → LLM call → parse → store. Each checkpoint writes progress to `observation_envelope.processing_state`.
- New worker resumes from the last completed checkpoint, not from scratch.
- If LLM call was the last completed step, we don't pay for it twice.

```python
# Pseudocode
async def process_observation_idempotent(observation_id: UUID):
    state = await load_state(observation_id)
    if state.completed: return  # already done
    
    if not state.redacted:
        await redact(observation_id)
        await update_state(observation_id, redacted=True)
    
    if not state.extracted:
        memories = await extract_with_llm(observation_id)
        await save_extracted(observation_id, memories)
        await update_state(observation_id, extracted=True)
    
    if not state.stored:
        await store(observation_id)
        await update_state(observation_id, stored=True, completed=True)
```

### 5. LLM provider outage

**Symptom:** OpenAI returns 429 or 503 for extended period.

**Behavior:**
- Per-provider circuit breaker. After 5 consecutive failures or >50% error rate over 30s, the breaker opens for 60s.
- While breaker open, extraction tasks are not started; they wait in the queue.
- Customer dashboard shows "Extraction backlog" banner when queue depth > 10k.
- After 5 minutes of provider outage, customers can opt-in fallback: try Anthropic → try local Llama (only for Enterprise).
- After 30 minutes outage on a tenant's BYOK provider, we email them.

**Customer-side BYOK consideration:**
- We never use a customer's BYOK key for any other tenant's traffic. Ever.
- If their BYOK key is rate-limited, we don't fall back to contexta's managed key without explicit opt-in. Customers control this in dashboard.

### 6. Postgres primary down

**Symptom:** Writes fail with connection refused or replication conflict.

**Behavior:**
- Gateway returns **503 Service Unavailable** for write endpoints with `Retry-After: 30`.
- Reads continue from replica (replica may be slightly behind, customer sees stale data with header `X-contexta-Stale: true`).
- Pager fires for on-call.
- Manual failover to HEL1 replica (RTO 15-30 min). Documented in runbook.
- After failover, the old primary is reseeded from the new primary as the new replica.

**Why not auto-failover:** Postgres physical replication failover has split-brain risk. We don't trust Patroni or repmgr enough at v1 to do this automatically. Manual is acceptable at our SLA.

### 7. Redis primary down

**Symptom:** Rate limit and quota lookups fail.

**Behavior:**
- Gateway has a "Redis fail-open" mode: if Redis is unreachable for >1s, requests pass without rate limiting (with a `X-contexta-Degraded: rate-limit` header).
- This degrades security but not correctness. The risk is brief abuse during the window.
- Meter events buffer to local file (gateway has 100 MB local buffer). When Redis returns, buffer flushes.
- Sentinel promotes replica. Total degradation: 30s expected.

### 8. Disk full on Postgres

**Symptom:** Writes fail with disk full error.

**Behavior:**
- Alert at 70%, page at 85%, automated read-only mode at 95%.
- Read-only mode: writes return 503; reads continue.
- Capacity-add takes priority over all other work.
- Long-term: monthly partition rotation + S3 archive of old data prevents this scenario.

### 9. Schema drift from extraction LLM

**Symptom:** LLM returns malformed structured_data that doesn't match registered schema.

**Behavior:**
- Extraction worker tries up to 3 times with reprompting ("Your previous response was invalid: <error>. Please return valid JSON matching the schema.").
- If all retries fail, store memory with raw content and `structured_data = null` and `flag = 'schema_validation_failed'`.
- Memory still stored, still searchable. Not silently dropped.
- Dashboard shows flagged memories so the customer can inspect.
- After 100 flagged memories of the same flag, we email the customer.

### 10. Bad user_id (unparseable UUID, doesn't exist in customer's records)

**Symptom:** Customer sends user_id that's malformed or never seen before.

**Behavior:**
- Malformed (not a UUID): 422 with `error.code = "INVALID_USER_ID"`.
- Valid UUID but never seen before: **accept it**. contexta doesn't authenticate the customer's end-users; we just store memories scoped to whatever ID they pass.
- Customers track their own user mapping. We document this clearly.

### 11. Quota exceeded

**Symptom:** Customer hits plan limit.

**Behavior:**
- Hard cap on: 429 with `error.code = "QUOTA_EXCEEDED"`, `Retry-After: <seconds-to-period-rollover>`, dashboard banner, email to org admins.
- Soft cap on (default): allow with `X-contexta-Quota-Used: 1.04` header. Overage billed at end of cycle.
- 80% threshold: email + dashboard banner.
- 100% threshold: email + dashboard banner + (if hard cap) start 429.

### 12. Rate limit exceeded

**Symptom:** Customer's agent loop is too aggressive.

**Behavior:**
- 429 with `Retry-After: <seconds>` based on token bucket refill rate.
- SDK auto-retries with backoff up to 3 times.
- After 3 retries, error surfaces to customer code.
- Repeated rate-limiting (>1000 events in 24h for one key) shows up as a dashboard health warning.

### 13. Sensitive data leaked through extraction

**Symptom:** Secondary scan after LLM extraction finds redacted-pattern in the memory content.

**Behavior:**
- Memory discarded entirely.
- Audit log entry: `operation_type = "sensitive_data_discarded"`, details include pattern type but NOT the value.
- Dashboard counter increments (so customer can see "we caught X secrets this month").
- We never store the value, never log it.

### 14. Concurrent modification (two writers update same memory)

**Symptom:** Two extraction workers produce conflicting updates to the same entity.

**Behavior:**
- Optimistic concurrency: every UPDATE includes `WHERE updated_at = $expected_updated_at`.
- If 0 rows affected, we re-fetch and re-merge.
- Merge logic: prefer higher confidence; if equal, prefer more recent extraction.
- After 3 merge retries, we give up and log a warning. The newer write may be discarded (rare; logged for inspection).

### 15. Customer's API key compromised

**Symptom:** Customer detects unexpected usage.

**Behavior:**
- Customer revokes via dashboard or CLI: revoked_at timestamp set, status = 'revoked'.
- Gateway cache invalidated within 60 seconds (or instant via Redis pub-sub).
- Customer rotates: new key issued, old key valid for 24 hours unless force-revoked.
- We do not auto-detect compromised keys at v1. Future: detect anomaly patterns (sudden geo shift, rate spike).


## Idempotency contract

### Header
```
Idempotency-Key: <client-generated UUID v4 or v7>
```

Required for retries. Recommended for all writes. Optional but suggested by SDKs (auto-generated if not supplied).

### Storage
A `idempotency_record` table:

```sql
CREATE TABLE idempotency_record (
  key             VARCHAR(80) PRIMARY KEY,
  organization_id UUID NOT NULL,
  endpoint        VARCHAR(80) NOT NULL,
  request_hash    CHAR(64) NOT NULL,           -- sha256 of canonical body
  response_status SMALLINT NOT NULL,
  response_body   JSONB NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL,
  expires_at      TIMESTAMPTZ NOT NULL          -- +24 hours
);

CREATE INDEX ix_idempotency_record_expires ON idempotency_record (expires_at);
```

A maintenance job deletes expired rows hourly.

### Replay semantics

- Same key + same body hash → return original response unchanged.
- Same key + different body hash → 409 `IDEMPOTENCY_CONFLICT` with `error.original_request_id`.
- Same key, original was not yet finalized (in flight) → 409 `IDEMPOTENCY_IN_FLIGHT`, customer should retry after `Retry-After: 5`.

### What's idempotent

| Endpoint | Idempotent? | Notes |
|---|---|---|
| POST /v1/observations | Yes | Same key → same job_id, even if processing not done |
| POST /v1/observations/batch | Yes | Returns same batch result |
| POST /v1/sessions | Yes | Same key → same session_id |
| POST /v1/memories/{id}/pin | Yes | Naturally idempotent |
| POST /v1/memories/{id}/unpin | Yes | |
| POST /v1/memories/{id}/archive | Yes | |
| POST /v1/memories/{id}/restore | Yes | |
| DELETE /v1/memories/{id} | Yes | Second call returns 404 (or 200 if `if-exists=true`) |
| POST /v1/keys | No | Each call creates a new key |
| POST /v1/policies | Partial | Same name+body → return existing |

## Failsafe summary table

| Component | Primary | Failsafe | Recovery time |
|---|---|---|---|
| SDK → Gateway | Direct HTTP | Local durable buffer | Seconds to hours |
| Gateway → Data plane | Direct HTTP | Redis Stream `writes:queue` | Sub-second |
| Data plane → Postgres | Direct SQL | Transaction rollback + retry | Sub-second |
| Worker LLM call | OpenAI | Circuit breaker + Anthropic fallback (Enterprise) | 30s |
| Postgres primary | FSN1 | HEL1 replica failover | 15-30 min manual |
| Redis primary | Sentinel auto-promote replica | 30s |
| Quota check | Redis | Fail-open with degraded header | Instant |
| Rate limit | Redis | Fail-open with degraded header | Instant |
| Meter event emission | Redis Stream | Local file buffer on gateway | Until Redis returns |
| Embedding generation | OpenAI | Queue for retry, store memory without embedding | Until provider returns |
| Stripe webhook | Stripe → us | Reconciliation job hourly | Hour |
| DNS | Cloudflare | Hetzner DNS as backup | Minutes |

## Observability of failures

Every failure is recorded:

1. **Sentry** — exception class, request_id, tenant_id, sanitized stack.
2. **Audit log** — when customer-relevant (key revoke, schema validation fail, sensitive data discard).
3. **Customer dashboard** — health page with last 30 days of error counts per category.
4. **Webhook** (planned post-launch) — customer subscribes to `failure.observation_dropped`, `failure.extraction_failed`, etc.
5. **Email** — on threshold-crossing failures (10+ in an hour).

The customer should never have to ask "did my data make it?". They have the request_id, they can query, they get notified on failures.

## What we cover that we don't market loudly

These are baked in but not marketed prominently because boasting about reliability invites scrutiny:

- Cross-region replica with 5-min RPO.
- WAL backup to S3 every 5 minutes.
- Hourly base backup.
- Quarterly disaster recovery game days.
- 24-hour idempotency key window.
- 1000-observation client-side buffer.
- Exponential backoff with jitter on every retry.
- Circuit breakers around every external dependency.
- Optimistic concurrency on every memory update.
- Read-only mode when disk fills up.
- Fail-open rate limiting (with degraded header).

We're confident in these. They're table stakes for a real B2B product.
