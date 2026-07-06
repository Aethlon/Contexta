# 07 — Metering and Billing

This document covers how contexta measures customer usage, enforces quotas, and charges via Stripe. Accuracy is the first-order property: a customer must be able to reconcile their bill against their own logs to the request.

## Decisions of record

1. **Every metered request emits exactly one usage event.** No batching at emission time. Events go straight to Redis Streams.
2. **Aggregation is async and idempotent.** A separate aggregator rolls events into hourly and daily buckets. Reprocessing is safe.
3. **Stripe metered billing using usage records.** We push aggregates to Stripe at the close of each billing cycle and on demand for dashboard previews.
4. **Hard caps are opt-in per project.** When enabled, the gateway returns 429 once limit is hit. Default is soft cap with overage billing.
5. **Customers can self-serve plan changes.** Stripe Customer Portal handles upgrades/downgrades. Limits change at next billing cycle for downgrades, immediately for upgrades.
6. **No silent surcharges.** Every overage line item appears separately on the invoice with a clear unit and quantity.


## Data model

Two new tables, plus a denormalized rollup for fast dashboard reads.

### `usage_event` — append-only fact table

```sql
CREATE TABLE usage_event (
  id              UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  project_id      UUID NOT NULL,
  api_key_id      UUID NOT NULL,
  user_id         UUID,                       -- end-user the agent acts for, nullable
  endpoint        VARCHAR(80) NOT NULL,
  method          VARCHAR(10) NOT NULL,
  classification  VARCHAR(20) NOT NULL,       -- 'observation' | 'retrieval' | 'rerank' | 'memory_write' | 'memory_read'
  units           INTEGER NOT NULL,           -- 1 for single, N for batch
  bytes_in        INTEGER NOT NULL DEFAULT 0,
  bytes_out       INTEGER NOT NULL DEFAULT 0,
  llm_tokens_in   INTEGER NOT NULL DEFAULT 0,
  llm_tokens_out  INTEGER NOT NULL DEFAULT 0,
  latency_ms      INTEGER NOT NULL DEFAULT 0,
  status_code     SMALLINT NOT NULL,
  request_id      VARCHAR(40) NOT NULL,
  occurred_at     TIMESTAMPTZ NOT NULL,
  region          VARCHAR(20) NOT NULL
) PARTITION BY RANGE (occurred_at);

-- Monthly partitions
CREATE TABLE usage_event_2026_05 PARTITION OF usage_event
  FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE usage_event_2026_06 PARTITION OF usage_event
  FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
-- A maintenance task creates the next month's partition on the 25th

CREATE INDEX ix_usage_event_org_occurred ON usage_event (organization_id, occurred_at);
CREATE INDEX ix_usage_event_project_occurred ON usage_event (project_id, occurred_at);
CREATE INDEX ix_usage_event_request_id ON usage_event (request_id);
```

Partitioning by month means we can drop a partition older than retention without touching active data. Default retention: 90 days of raw events. After that, only rollups are kept.

### `usage_daily` — denormalized rollup

```sql
CREATE TABLE usage_daily (
  organization_id UUID NOT NULL,
  project_id      UUID,
  day             DATE NOT NULL,
  classification  VARCHAR(20) NOT NULL,
  units           BIGINT NOT NULL,
  llm_tokens_in   BIGINT NOT NULL,
  llm_tokens_out  BIGINT NOT NULL,
  bytes_in        BIGINT NOT NULL,
  bytes_out       BIGINT NOT NULL,
  request_count   BIGINT NOT NULL,
  cost_micros     BIGINT NOT NULL,            -- estimated cost in millionths of USD
  PRIMARY KEY (organization_id, project_id, day, classification)
);

CREATE INDEX ix_usage_daily_org_day ON usage_daily (organization_id, day);
```

Dashboard reads `usage_daily` exclusively. It's small (few rows per tenant per day) and lookups are millisecond.

### `usage_period` — billing-cycle rollup

```sql
CREATE TABLE usage_period (
  organization_id UUID NOT NULL,
  period_start    DATE NOT NULL,
  period_end      DATE NOT NULL,
  plan_code       VARCHAR(40) NOT NULL,
  status          VARCHAR(20) NOT NULL,        -- 'open' | 'closed' | 'invoiced'
  observations    BIGINT NOT NULL DEFAULT 0,
  retrievals      BIGINT NOT NULL DEFAULT 0,
  reranks         BIGINT NOT NULL DEFAULT 0,
  memory_writes   BIGINT NOT NULL DEFAULT 0,
  active_memories BIGINT NOT NULL DEFAULT 0,   -- snapshot at period_end
  overage_cents   BIGINT NOT NULL DEFAULT 0,
  invoice_id      VARCHAR(80),                  -- Stripe invoice
  created_at      TIMESTAMPTZ NOT NULL,
  closed_at       TIMESTAMPTZ,
  PRIMARY KEY (organization_id, period_start)
);
```

`status` transitions: `open` → `closed` (cycle ended, ready to invoice) → `invoiced` (Stripe accepted).


## Pipeline

```
Customer request
       │
       ▼
[ Edge gateway: handles request, emits at end ]
       │
       ▼     XADD meter:events  { json event }
[ Redis Stream: meter:events ]
       │
       ├─→ [ Aggregator (Go): XREADGROUP ]
       │      │
       │      ├─→ [ Postgres: INSERT INTO usage_event ]
       │      │
       │      └─→ [ Redis: HINCRBY quota:obs:<tenant>:<month> 1 ]
       │
       └─→ [ Async: every 5 min, sweep usage_event into usage_daily upserts ]
              │
              └─→ [ Async: at billing-cycle boundary, populate usage_period ]
                     │
                     └─→ [ Stripe: usage_records.create() per metric ]
```

### Why Redis Stream first

The gateway must respond to the customer in <50 ms. We cannot block on Postgres for the meter write. Redis Stream:
- Sub-millisecond enqueue.
- Persistent (survives Redis restart with AOF).
- Consumer groups for at-least-once semantics.
- Replayable for backfill.

### The aggregator

A Go process (`services/aggregator/`) runs as a singleton with leader election (Redlock). It does two jobs:

1. **Drain `meter:events` stream** into `usage_event` table. Buffered: every 1000 events or 1 second, whichever first. Uses `INSERT ... ON CONFLICT DO NOTHING` keyed on `id` for idempotency.
2. **Roll up `usage_event` into `usage_daily`** every 5 minutes for the current day, every hour for prior days (until day closes at midnight UTC).

Pseudocode:

```go
func (a *Aggregator) drainStream(ctx context.Context) error {
    for {
        msgs, err := a.redis.XReadGroup(ctx, &redis.XReadGroupArgs{
            Group:    "aggregator",
            Consumer: a.id,
            Streams:  []string{"meter:events", ">"},
            Count:    1000,
            Block:    1 * time.Second,
        }).Result()
        if err != nil { /* handle */ }

        events := parseMessages(msgs)
        if err := a.db.InsertEvents(ctx, events); err != nil { /* handle */ }

        ids := messageIDs(msgs)
        a.redis.XAck(ctx, "meter:events", "aggregator", ids...)
    }
}

func (a *Aggregator) rollupCurrent(ctx context.Context) error {
    today := time.Now().UTC().Truncate(24 * time.Hour)
    return a.db.UpsertDailyForRange(ctx, today, today.Add(24*time.Hour))
}
```

### Quota counters

Hot path: gateway looks up `HGET quota:obs:<tenant>:<period_start>` per request. The aggregator increments this in the same loop as the Postgres insert.

Why two counters (Redis and Postgres rollup)? Redis is the fast path, used to enforce hard caps in real time. Postgres is the source of truth used for billing. They reconcile every 5 minutes; if drift exceeds 1%, an alert fires.

## Stripe integration

### Plans and prices

Each tier is one Stripe Product with one base Price (recurring) plus three usage-based Prices for overages:

```
Product: contexta Solo Pro
  Prices:
    - solo-pro-base       $69.00 / month, recurring
    - solo-pro-obs-over   $0.002 / unit, metered, monthly aggregation
    - solo-pro-ret-over   $0.0001 / unit, metered, monthly aggregation
    - solo-pro-rerank-over $0.003 / unit, metered, monthly aggregation
```

A subscription has the base price + zero or more overage prices attached. Overage prices are only added if the customer enables soft cap.

### Webhooks we listen to

| Event | Action |
|---|---|
| `customer.subscription.created` | Create `organization` row, set plan |
| `customer.subscription.updated` | Update `organization.plan_code` |
| `customer.subscription.deleted` | Mark org `cancelled`, schedule data export job |
| `invoice.payment_succeeded` | Mark `usage_period` invoiced |
| `invoice.payment_failed` | Email + dashboard banner; after 7 days, downgrade to Hobby |
| `customer.subscription.trial_will_end` | Email reminder |

Webhook handler is in Python (`contexta/api/routes/billing.py`), behind Stripe signature verification.

### Reporting usage to Stripe

At the end of each billing cycle:

1. Aggregator marks `usage_period.status='closed'`.
2. A worker iterates closed-but-not-invoiced periods.
3. For each period, computes overage units beyond plan limits.
4. Calls `stripe.SubscriptionItem.create_usage_record(...)` per metric.
5. Stripe generates the invoice.
6. Webhook `invoice.payment_succeeded` flips status to `invoiced`.

```python
# contexta/services/stripe_billing.py (simplified)
async def report_period(period: UsagePeriod) -> None:
    plan = PLANS[period.plan_code]
    obs_overage = max(0, period.observations - plan.included_observations)
    if obs_overage > 0:
        await stripe.SubscriptionItem.create_usage_record_async(
            subscription_item=period.stripe_observation_item_id,
            quantity=obs_overage,
            timestamp=int(period.period_end.timestamp()),
            action="set",
        )
    # Same for retrievals, reranks, memory storage
```

`action="set"` (not "increment") so reprocessing is idempotent.


## Hooks (auto-update of dashboard and customer)

Customer-visible hooks fire on:

1. **80% threshold reached** for any plan dimension → email + dashboard banner.
2. **100% threshold reached** → email; if hard cap, 429 starts; if soft cap, banner with running overage estimate.
3. **Plan upgrade applied** → email confirmation, dashboard banner clears.
4. **Plan downgrade scheduled** → email confirmation with effective date.
5. **Invoice generated** → email + dashboard receipt link.
6. **Payment failed** → email + dashboard banner.
7. **API key created/rotated/revoked** → email to org admins (configurable).

Internal hooks fire on:

- **Per-tenant cost > 80% of revenue** for current period → page on-call.
- **Aggregator lag > 60 s** → page on-call.
- **Stripe webhook signature verification fails** → page on-call.
- **Billing period close fails** → page on-call, do not retry blindly.

Hooks are emitted as async tasks in Celery and consumed by:
- Email sender (Postmark or Resend).
- In-app notifications (Postgres `notification` table, polled by dashboard).
- Slack incoming webhook (for internal alerts).

## Accuracy guarantees

We commit publicly to:

1. **Counts shown in the dashboard equal counts in your invoice.** No discrepancy beyond ±1 event per million (which is the at-most-once edge of the streaming pipeline).
2. **Every charged event is auditable.** Customers can call `GET /v1/usage/events` and reconcile against their own logs.
3. **Refunds for billing errors.** If we charge in error, we refund + 10% credit, automatic, no escalation needed.

These are codified in the contexta ToS.

## Accuracy implementation

To keep these guarantees, the system uses:

1. **Idempotency keys on event emission.** The gateway generates `event_id = uuid7()`. Postgres inserts with `ON CONFLICT (id) DO NOTHING`.
2. **At-least-once stream consumption.** XACK only after successful Postgres insert.
3. **Reconciliation job.** Daily at 02:00 UTC, the aggregator compares stream cardinality to Postgres event count for the previous day. Discrepancies > 0.001% page on-call.
4. **Stripe usage records use action="set"**, not "increment", with the period_end timestamp. Reprocessing is safe.

## Customer dashboard usage view

Every metered customer sees on `/dashboard/usage`:

- **Current period summary card** (matches `GET /v1/usage`): plan, period range, used vs limit per dimension.
- **Daily breakdown chart**: stacked bars per classification for the last 30 days. Source: `usage_daily`.
- **Per-key breakdown table**: which API key consumed what. Filter by project.
- **Per-endpoint table**: top 20 endpoints by request count. Useful for spotting agent loops.
- **Cost estimate**: end-of-period cost projection if usage continues at current pace.
- **Hard cap toggle**: per-project, per-dimension. Off by default.
- **Export**: CSV download of last 30 days of `usage_event` rows. Throttled to once per hour per org.

## What gets free billing capacity

- **First 7 days of every month** of the customer's signup tier are not charged for overage. This is the "settle into your traffic" period for new customers.
- **Customer-reported bugs that produce inflated counts** are credited at next invoice. The customer files via `/v1/billing/dispute` (form in dashboard).
- **Internal smoke tests** run from a fixed set of internal API keys, never billed.
- **Health checks and metrics scrapes** are not billed (gateway never emits meter event for `/healthz`, `/metrics`, `/readyz`).

## Why we did not pick alternatives

| Considered | Rejected because |
|---|---|
| **Stripe Billing Meters (newer)** | Newer API, less mature SDK, prefer the proven usage-records flow at v1 |
| **Orb / Lago / Metronome (3rd-party usage billing)** | Overkill for first 1000 customers; another vendor dependency; their pricing eats margin |
| **In-process Postgres counters only** | Hot path latency unacceptable; Postgres write per request would saturate the disk |
| **Kafka instead of Redis Streams** | Operational weight too high for v1 traffic; Redis Stream is sufficient until 50k events/sec |
| **Per-request synchronous Stripe metered call** | Stripe rate-limits aggressively; reporting at cycle close is the documented pattern |
