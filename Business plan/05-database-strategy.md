# 05 — Database Strategy

This document covers the database from the bare-metal level up: hardware, replication, tiered storage, indexing, isolation, backup, and how the data plane talks to it.

## Decisions of record

1. **Self-hosted Postgres 16 with pgvector**, single primary + streaming physical replica. No managed Postgres at any tier (Neon, Supabase, RDS).
2. **Bare-metal Hetzner AX52** for primary and replica at launch. Upgrade to AX102 (128 GB RAM) when active memory count exceeds 5M tenant-wide.
3. **One database per region.** Tenants are colocated in a shared database with `organization_id` row-level isolation. No per-tenant schema or per-tenant database.
4. **Tiered storage via table partitioning by `memory_state`.** Hot, warm, cold partitions. Archived rows move to S3-compatible object storage.
5. **HNSW for hot/warm vector indexes, IVFFlat for cold.** Different recall/latency tradeoffs match the access pattern.
6. **No sharding at v1.** A single AX102 holds 50M+ memories with HNSW comfortably. We add read replicas before we shard.
7. **Read replicas for hot reads only.** The Go data plane reads from the replica via PgBouncer. Writes always go to primary.

## Hardware

### Primary (Hetzner AX52, FSN1, ~$115/mo)

- AMD Ryzen 7 7700, 8 cores / 16 threads.
- 64 GB DDR5 ECC.
- 2× 1TB NVMe SSD in software RAID 1.
- 1 Gbps unmetered.
- Debian 12.

### Read replica (AX52, HEL1, ~$115/mo)

Same specs. Streaming replication from primary. Used for:
- Read traffic from Go data plane.
- Failover candidate.
- Automatic backup snapshots.

### Upgrade path

| Active memories tenant-wide | Recommended primary |
|---|---|
| < 5M | AX52 (64 GB) |
| 5M – 30M | AX102 (128 GB) |
| 30M – 200M | EX130-S (256 GB) |
| > 200M | Sharded across N AX102+ |

The "active memories tenant-wide" trigger is: total rows in `memory_record` across hot+warm partitions. We monitor this in Grafana and trigger upgrade at 80% of next tier.

## Tuning

`postgresql.conf` overrides for AX52 with 64 GB RAM:

```ini
shared_buffers = 16GB
effective_cache_size = 48GB
maintenance_work_mem = 2GB
work_mem = 32MB
max_connections = 200
random_page_cost = 1.1
effective_io_concurrency = 200
wal_buffers = 64MB
checkpoint_completion_target = 0.9
max_wal_size = 4GB
min_wal_size = 1GB
default_statistics_target = 200

# pgvector specific
hnsw.ef_search = 64
maintenance_work_mem = 2GB    # for HNSW index build

# replication
wal_level = replica
max_wal_senders = 5
hot_standby = on
synchronous_commit = on
synchronous_standby_names = 'CONTEXTA_replica_hel1'
```

PgBouncer in front, transaction mode, pool size 100. The Go data plane and Python API both connect through PgBouncer.

## Schema and tenant isolation

Every domain table has `organization_id UUID NOT NULL` plus a B-tree index on it. The `TenantScopedRepository` in Python and equivalent guards in the Go data plane (see [06-polyglot-services.md](./06-polyglot-services.md)) enforce that every query has `WHERE organization_id = $tenant`.

In addition, Postgres-level **row-level security** (RLS) is enabled as a defense-in-depth on production:

```sql
ALTER TABLE memory_record ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON memory_record
  USING (organization_id = current_setting('app.tenant_id')::uuid);
```

Each session sets `SET LOCAL app.tenant_id = '...'` at the start of every transaction. Even if application code forgets the WHERE clause, RLS prevents cross-tenant data exposure.

This is a belt-and-suspenders policy. We don't rely solely on RLS (it has a perf cost and edge cases) but we don't rely solely on the repository layer either.

## Tiered storage

The `memory_record` table is range-partitioned on `memory_state`:

```sql
CREATE TABLE memory_record (
  ...
) PARTITION BY LIST (memory_state);

CREATE TABLE memory_record_active   PARTITION OF memory_record FOR VALUES IN ('active');
CREATE TABLE memory_record_warm     PARTITION OF memory_record FOR VALUES IN ('warm');
CREATE TABLE memory_record_cold     PARTITION OF memory_record FOR VALUES IN ('cold');
CREATE TABLE memory_record_archived PARTITION OF memory_record FOR VALUES IN ('archived');
```

| Partition | Storage | Vector index | RAM footprint | Latency target |
|---|---|---|---|---|
| `memory_record_active` | NVMe local | HNSW (m=32, ef_construction=128) | Pinned in `shared_buffers` | p50 < 30 ms, p99 < 150 ms |
| `memory_record_warm` | NVMe local | HNSW (m=16, ef_construction=64) | OS cache, lazy load | p50 < 80 ms, p99 < 300 ms |
| `memory_record_cold` | NVMe local | IVFFlat (lists=200) | On disk, no pin | p50 < 500 ms, p99 < 2 s |
| `memory_record_archived` | S3 + metadata stub | none | none | sync read disabled, export only |

When the decay engine transitions a memory between states (`active → warm`, etc.), Postgres automatically routes the row to the correct partition via `UPDATE memory_record SET memory_state = 'warm' WHERE id = ...`. No data move at the application layer.

Archived rows are moved to S3 monthly by a maintenance job:

```python
# Pseudo-code in contexta/workers/archive_tasks.py
async def archive_cold_to_s3(tenant_id: UUID):
    cold_rows = await query("SELECT * FROM memory_record_archived WHERE organization_id = $1 AND archived_at < NOW() - INTERVAL '30 days'", tenant_id)
    s3_key = f"archive/{tenant_id}/{date.today().isoformat()}.jsonl.gz"
    await write_to_s3(s3_key, cold_rows)
    await query("DELETE FROM memory_record_archived WHERE organization_id = $1 AND id = ANY($2)", tenant_id, [r.id for r in cold_rows])
    await query("INSERT INTO archive_index (tenant_id, s3_key, row_count, archived_at) VALUES ...")
```

A `memory_record_stub` table keeps a minimal metadata row so explainability and timeline queries still work without restoring from S3.

## Indexes (current and planned)

Already in the initial migration:

```sql
CREATE INDEX ix_memory_record_embedding_hnsw
  ON memory_record USING hnsw (embedding vector_cosine_ops)
  WITH (m=16, ef_construction=64);

CREATE INDEX ix_memory_record_org_user_type
  ON memory_record (organization_id, user_id, memory_type);

CREATE INDEX ix_memory_record_org_user_state
  ON memory_record (organization_id, user_id, memory_state);

CREATE INDEX ix_memory_record_org_valid_to_partial
  ON memory_record (organization_id, valid_to)
  WHERE valid_to IS NULL;

CREATE INDEX ix_memory_record_search_vector_gin
  ON memory_record USING gin(search_vector);
```

Additional indexes planned for the data plane (added in a v0.2 migration):

```sql
-- Per-partition HNSW with different params
CREATE INDEX ix_active_emb_hnsw ON memory_record_active
  USING hnsw (embedding vector_cosine_ops) WITH (m=32, ef_construction=128);

CREATE INDEX ix_warm_emb_hnsw ON memory_record_warm
  USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);

CREATE INDEX ix_cold_emb_ivfflat ON memory_record_cold
  USING ivfflat (embedding vector_cosine_ops) WITH (lists=200);

-- Speed up retrieval feedback aggregations
CREATE INDEX ix_feedback_org_signal_retrieved
  ON retrieval_feedback (organization_id, signal, retrieved_at);

-- Speed up audit timeline queries
CREATE INDEX ix_audit_org_target_created
  ON audit_log (organization_id, target_id, created_at);

-- Speed up entity graph traversal in retrieval
CREATE INDEX ix_edge_org_source ON entity_edge (organization_id, source_entity_id);
CREATE INDEX ix_edge_org_target ON entity_edge (organization_id, target_entity_id);
```

## Hybrid retrieval SQL (the canonical query)

The Python `RetrievalEngine` today fetches candidates and scores in Python. That's fine for correctness, but production-grade retrieval pushes the work into a single SQL query. The Go data plane runs this:

```sql
WITH semantic AS (
  SELECT id,
         1 - (embedding <=> $1::vector) AS semantic_score
  FROM memory_record
  WHERE organization_id = $2
    AND user_id = $3
    AND valid_to IS NULL
    AND is_archived = false
    AND ($4::text[] IS NULL OR memory_type = ANY($4))
    AND ($5::text[] IS NULL OR tags && $5)
  ORDER BY embedding <=> $1::vector
  LIMIT 200
),
keyword AS (
  SELECT id,
         ts_rank_cd(search_vector, plainto_tsquery('english', $6)) AS keyword_score
  FROM memory_record
  WHERE organization_id = $2
    AND user_id = $3
    AND valid_to IS NULL
    AND is_archived = false
    AND search_vector @@ plainto_tsquery('english', $6)
  ORDER BY keyword_score DESC
  LIMIT 200
),
graph AS (
  SELECT DISTINCT mel.memory_id AS id,
         1.0 AS graph_score
  FROM memory_entity_link mel
  JOIN entity e ON e.id = mel.entity_id
  WHERE mel.organization_id = $2
    AND e.id = ANY($7::uuid[])
),
combined AS (
  SELECT id,
         COALESCE(semantic_score, 0) AS sem,
         COALESCE(keyword_score, 0)  AS kw,
         COALESCE(graph_score, 0)    AS gr
  FROM (
    SELECT id, semantic_score, NULL::float AS keyword_score, NULL::float AS graph_score FROM semantic
    UNION ALL
    SELECT id, NULL, keyword_score, NULL FROM keyword
    UNION ALL
    SELECT id, NULL, NULL, graph_score FROM graph
  ) u
)
SELECT m.*,
       (
         0.40 * MAX(c.sem) +
         0.05 * MAX(c.kw) +
         0.25 * MAX(c.gr) +
         0.20 * m.importance +
         0.10 * EXP(-LN(2) * EXTRACT(EPOCH FROM NOW() - m.created_at)/86400/30)
       ) - (CASE WHEN m.memory_state = 'cold' THEN 0.3 ELSE 0 END) AS score
FROM combined c
JOIN memory_record m ON m.id = c.id
GROUP BY m.id
ORDER BY score DESC
LIMIT $8;
```

This single query does the full hybrid retrieval. Latency on AX52 with 1M memories per tenant: ~30-80 ms p99.

If the customer enabled `rerank=true`, the Go service takes the top 50 results from this query, calls the LLM rerank endpoint with `messages` constructed from titles + content, and re-orders. Rerank adds ~400-700ms.

## Replication and backup

### Replication
- Streaming physical replication (WAL shipping) from primary to replica.
- Synchronous commit on replica's confirmation. Yes this slows writes ~5ms but it gives durability.
- Replica lag monitored. >10s lag pages on-call.

### Backup
- **WAL archiving** to S3-compatible storage (Hetzner Storage Box) every 5 minutes.
- **Daily full base backup** via `pg_basebackup` to the same S3 bucket.
- **Retention**: 30 days of daily base backups, 7 days of WAL.
- **Recovery objective**: RPO 5 minutes, RTO 30 minutes (for full restore).

### Disaster recovery test
- Quarterly: spin up a temporary box, restore the latest backup, run a small read query, decommission. The runbook is in [13-operations-and-security.md](./13-operations-and-security.md).

## Connection pooling

PgBouncer in transaction mode:

```ini
# pgbouncer.ini
[databases]
CONTEXTA_prod = host=db-primary.fsn1.contexta.internal port=5432 dbname=CONTEXTA_prod
CONTEXTA_prod_ro = host=db-replica.hel1.contexta.internal port=5432 dbname=CONTEXTA_prod

[pgbouncer]
listen_port = 6432
listen_addr = *
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 2000
default_pool_size = 100
reserve_pool_size = 20
server_idle_timeout = 600
ignore_startup_parameters = extra_float_digits,application_name
```

The Python API uses `pool_size=20, max_overflow=10` (per-process) so 5 API instances × 30 = 150 connections. The Go data plane uses `pgxpool.Config.MaxConns=80` per-instance, 2 instances = 160 connections. Total stays under 400, well under the PgBouncer cap of 2000.

## Index maintenance

HNSW indexes do not need REINDEX in normal operation, but vacuum and analyze do:

```sql
-- Run via cron / maintenance window
VACUUM (ANALYZE, VERBOSE) memory_record_active;
VACUUM (ANALYZE, VERBOSE) memory_record_warm;
ANALYZE memory_record_cold;
```

Daily at 03:00 UTC. The maintenance worker enqueues this.

## Migration strategy

Alembic. Every migration:

- Is reversible (`downgrade()` implemented).
- Is run against a staging clone of production before prod.
- Is idempotent (uses `IF NOT EXISTS`, `IF EXISTS`).
- Big migrations (renaming columns, large data backfills) use the **expand/contract pattern**: ship the schema change first with both old and new, deploy code that writes both, deploy code that reads new, then ship the migration that drops old.

We do not run migrations during peak hours unless they're tiny. Maintenance window: 03:00–05:00 UTC.

## Why we didn't pick alternatives

| Considered | Rejected because |
|---|---|
| **Neon (managed Postgres)** | Per-row pricing kills margin at 1M+ memories. No physical replica control. Branch-on-write is cute but not needed. |
| **Supabase** | Same as Neon plus opinionated auth that conflicts with our auth. |
| **AWS RDS Postgres** | 4–5x cost vs Hetzner bare metal for equivalent IO. |
| **CockroachDB** | Distributed Postgres-compatible but pgvector support immature. Operational complexity not justified. |
| **MongoDB Atlas Vector** | We need transactions across vector + relational. MongoDB's vector add-on is bolted on. |
| **Weaviate / Qdrant / Pinecone** | Separate vector DB means we'd be syncing two stores. pgvector keeps it transactional and saves a system. |
| **Per-tenant schema (multi-schema)** | Operational nightmare at 1k+ tenants. Postgres catalog scales poorly past ~10k schemas. |
| **Per-tenant database** | Same as above plus connection pooling fragmentation. |

## Sharding plan (not v1)

When a single primary is no longer enough (we estimate this at ~30M active memories tenant-wide, projected month 18+), we shard by `organization_id` hash:

- Tenants → consistent hash → 1 of N shards.
- A small "tenant directory" service maps `tenant_id → shard_endpoint`.
- The Go data plane already takes a connection per query, so it just selects the pool by shard.
- Cross-tenant queries (admin only) fan out to all shards.

Designing for sharding now: every query already has `organization_id` in the WHERE; never JOIN across tenants; never use sequences (use UUIDs). All current code is shard-friendly already.

## Cost ceiling

Database cost should not exceed 8% of MRR. At Year 1 MRR of $35k that's $2.8k/mo budget. Current usage:

- Primary AX52: $115/mo
- Replica AX52: $115/mo
- Storage Box (backup): $5/mo
- PgBouncer VM: $5/mo
- **Total: $240/mo (0.7% of MRR)**

Massive headroom. We won't outgrow this until ~Month 12.


## Memory row model: structured, not raw text

Memories are stored as **structured rows**, not text blobs. The structured fields enable retrieval, conflict resolution, and explainability that pure-text storage cannot.

Every memory row carries:

```json
{
  "id": "mem_01J...",
  "organization_id": "org_...",
  "project_id": "proj_...",
  "user_id": "u_...",
  "memory_type": "preference",
  "title": "Prefers Postgres",
  "content": "User prefers PostgreSQL over MongoDB for relational data.",
  "structured_data": {
    "subject": "user",
    "entity": "postgresql",
    "value": "likes",
    "context": "relational"
  },
  "tags": ["database", "tech-stack"],
  "session_id": "sess_...",
  "source_type": "user_explicit",
  "confidence": 0.92,
  "importance": 0.87,
  "utility_score": 0.0,
  "memory_state": "active",
  "is_pinned": false,
  "is_archived": false,
  "valid_from": "2026-04-12T18:32:11Z",
  "valid_to": null,
  "supersedes_memory_id": null,
  "cluster_id": "cluster_tech_stack",
  "embedding": [...1536...],
  "search_vector": "..."
}
```

The `structured_data` field is JSONB and lets us:
- Retrieve by entity name without reembedding.
- Detect contradictions deterministically (`subject + entity + value` collision).
- Render explainability with field-level breakdown.

When a custom schema is registered for a memory type, `structured_data` conforms to that schema and is validated.

## Row-key hierarchy

Every domain row carries the full hierarchy:

```
organization_id (tenant boundary, RLS-enforced)
    └── project_id (logical grouping)
        └── user_id (end-user attribution)
            └── memory_id (the row itself)
```

Queries always include at least `organization_id`. The repository layer enforces this. RLS catches gaps.

The `project_id` is the customer's choice — they create projects in the dashboard. A typical flow: one project per agent (e.g., "support-bot-prod", "support-bot-staging"). Memories are scoped to projects so customers can isolate experiments and run policies per project.

## Why no per-tenant or per-user databases

We considered three alternatives:

| Approach | Why rejected |
|---|---|
| Per-tenant database | Postgres catalog scales poorly past ~10k DBs; connection pool fragmentation; backup/restore complexity 100× per tenant |
| Per-tenant schema | Same problems; ALTER TABLE cascade across N schemas every migration |
| Per-user database | Would explode to millions of DBs at scale |
| Per-user schema | Same as above |

**Shared cluster with row keys + RLS** is the standard pattern for SaaS at our scale. Stripe, Linear, Vercel all do this.

## When sharding becomes relevant

We've designed for sharding from day 1 (every query has `organization_id`, no cross-tenant joins, UUIDs not sequences). We don't shard at v1.

Sharding triggers:
- Active memory count tenant-wide > 30M.
- Postgres primary CPU sustained > 70%.
- Queries on the busiest hour exceed replica capacity.

When triggered: hash `organization_id` to one of N shards. A small "tenant directory" service (built in Go, runs alongside the gateway) maps tenant → shard endpoint. The data plane already takes a connection per query; it just chooses pool by shard.

Until then, one shared cluster is correct.

## Cluster-first organization

Memories are grouped at three levels for retrieval efficiency:

### Level 1: memory_type
Every memory has a type from this fixed taxonomy:

```
preference | goal | project | relationship | event | episodic
skill | fact | pattern | contact | custom
```

Indexed via composite B-tree `(organization_id, user_id, memory_type)`.

### Level 2: cluster_id
Memories are grouped into **semantic clusters**, computed by the Semantic Cluster Engine. A cluster represents a coherent topic for a user (e.g., "tech_stack", "career_goals", "vendor_relationships"). Each cluster has a centroid embedding for cluster-routed retrieval.

| Trigger | Action |
|---|---|
| New memory's embedding within 0.7 cosine of an existing centroid | Add to that cluster, recompute centroid |
| New memory > 0.7 from any centroid | Create new cluster (if 3+ similar memories accumulate) |
| Cluster size drops below 3 | Dissolve, members revert to "uncategorized" |
| Memory archived or deleted | Removed from cluster, centroid recomputed |

Clusters are scoped per (organization_id, user_id). They're stored in `semantic_cluster` table; membership in `cluster_membership`.

### Level 3: graph edges
Entities and memories form a graph via `entity` and `entity_edge` tables. Edges have typed relationships (`USES`, `WORKS_ON`, `LIKES`, `DEPENDS_ON`, `OWNS`, `SUPERSEDED_BY`, `RELATED_TO`).

The retrieval engine traverses the graph up to a configurable depth (default 1, max 3) when seeded with entities matched from the query.

## Validity timestamps

Every memory has `valid_from` and `valid_to`:

- `valid_from` defaults to extraction time, can be backdated by metadata for backfilled observations.
- `valid_to` is null for current truth; set when superseded by a newer contradicting memory.

Retrieval defaults to `valid_to IS NULL` (current truth only). Customers can request historical truth via `include_historical=true`.

The `supersedes_memory_id` column links the new memory to the one it replaced. Query the chain for full supersession history (used in `explain()`).