# 12 — Deployment Topology

This document covers where every component runs, what hardware it sits on, how the network is laid out, and how the data isolation requirements are met.

## Decisions of record

1. **Self-hosted on Hetzner dedicated and Hetzner Cloud** for v1. AWS only for the US edge gateway in month 4.
2. **EU primary in FSN1 (Falkenstein, Germany)**, replica in HEL1 (Helsinki, Finland).
3. **Each tier of compute lives on its own machine class.** No cohabiting Postgres with the API tier.
4. **Private network between all internal services.** External traffic terminates at the gateway only.
5. **TLS everywhere.** Edge → public via Let's Encrypt or Cloudflare Origin Cert. Internal mTLS by month 3.
6. **Cloudflare in front for DDoS, WAF, anycast routing.**

## v1 topology (months 1–6)

### Region: EU-FSN1 (primary)

```
Internet
    │
    ▼
[ Cloudflare ]                         (DDoS, WAF, anycast)
    │
    ▼
[ Hetzner FSN1 ────────────────── private VLAN ─────────── ]
    │                                                       │
    │ public IP                                              │
    ▼                                                       │
┌───────────────────┐                                       │
│ Edge Gateway × 2  │  CCX13 (2 vCPU, 8 GB)                 │
│  (Go)             │  $10/mo each                          │
│                   │                                       │
│ Caddy: TLS,       │                                       │
│ HTTP/2, HTTP/3    │                                       │
└─────────┬─────────┘                                       │
          │ private IP                                      │
          ├──────────────────────────────────────────────────┐
          │                                                  │
          ▼                                                  ▼
┌─────────────────────┐              ┌────────────────────────┐
│ Data Plane × 2      │              │ Python API × 3         │
│ (Go)                │              │ (FastAPI)              │
│ CCX33 (8/32)        │              │ CCX23 (4/16)           │
│ $60/mo each         │              │ $30/mo each            │
└──────────┬──────────┘              └────────────┬───────────┘
           │                                      │
           │ pgbouncer                            │
           ▼                                      ▼
   ┌──────────────────────────────────────────────────────┐
   │                                                      │
   │  PgBouncer pool (1 small VM)                         │
   │  CCX13 + Postgres connection pool                    │
   │  $10/mo                                              │
   │                                                      │
   └────────────────────┬─────────────────────────────────┘
                        │
                        ▼
              ┌─────────────────────┐
              │ Postgres Primary    │
              │ AX52 (8c/64GB/2TB)  │
              │ $115/mo             │
              │ pgvector + pg_trgm  │
              └─────────┬───────────┘
                        │ streaming WAL
                        ▼
              ┌─────────────────────┐
              │ Postgres Replica    │
              │ AX52 (HEL1 region)  │
              │ $115/mo             │
              └─────────────────────┘

   ┌──────────────────┐    ┌──────────────────┐
   │ Redis Primary    │    │ Redis Replica    │
   │ CCX23 (4/16)     │    │ CCX13 (2/8)      │
   │ $30/mo           │    │ $10/mo           │
   └──────────────────┘    └──────────────────┘
                       
   ┌─────────────────────────────────────────┐
   │ Worker pool (Celery, Python)            │
   │  - Always-on × 2: CCX23 ($30/mo each)   │
   │  - Burst pool: CCX13, KEDA-scaled 0–10  │
   │  - Maintenance: CCX13 ($10/mo)          │
   └─────────────────────────────────────────┘
                       
   ┌─────────────────────────────────────────┐
   │ Aggregator (Go, singleton w/ Redlock)   │
   │ CCX13 $10/mo                            │
   └─────────────────────────────────────────┘
                       
   ┌─────────────────────────────────────────┐
   │ Object storage (Hetzner Storage Box)    │
   │ 1 TB $5/mo                              │
   │ S3-compatible, hosts archives + WAL     │
   └─────────────────────────────────────────┘
```

Total monthly: **~$615**.

### Network layout

- All Hetzner Cloud VMs and Hetzner Bare Metal are connected via a private vSwitch in FSN1.
- HEL1 replica connects via Hetzner private connect (cross-region private link).
- Only the edge gateway has a public IP. Everything else is private-only.
- Cloudflare in front provides:
  - DNS for `*.contexta.dev`.
  - DDoS L3/L4/L7 protection.
  - WAF rules (block common exploits, geo block at request).
  - Edge caching for static dashboard assets.

### Internal DNS

Internal services use private DNS records:

| Hostname | Resolves to |
|---|---|
| `gateway.fsn1.contexta.internal` | edge gateway VIP |
| `api.fsn1.contexta.internal` | Python API LB |
| `data.fsn1.contexta.internal` | Go data plane LB |
| `db.fsn1.contexta.internal` | PgBouncer (writes) |
| `db-ro.fsn1.contexta.internal` | PgBouncer (reads, replica) |
| `redis.fsn1.contexta.internal` | Redis primary |
| `redis-ro.fsn1.contexta.internal` | Redis replica |

Hetzner private DNS or self-hosted CoreDNS.


## Container orchestration

### Decision: Docker Swarm at v1, migrate to k3s by month 9

**Why not Kubernetes / EKS / GKE at v1?**
- 4-week setup vs 4-day setup.
- $200+/mo control plane cost on managed k8s.
- Operational complexity for a 12-VM fleet.

**Why Docker Swarm?**
- Built into Docker. No extra install.
- Service definitions in YAML same shape as docker-compose.
- Rolling updates with health checks.
- Secrets and configs first-class.
- Honest tradeoff: no autoscaling on metrics out of the box. We use a small KEDA-equivalent service for queue-depth scaling.

**Why migrate to k3s by month 9?**
- KEDA, OpenTelemetry, cert-manager, monitoring stack ecosystem is k8s-native.
- We hire SRE around month 8; they'll expect k8s.
- k3s is tiny (60 MB binary), fits Hetzner well, no managed-control-plane cost.

### Swarm stack file

```yaml
# stack.prod.yml
version: "3.9"
services:

  gateway:
    image: registry.contexta.dev/gateway:1.0.0
    deploy:
      replicas: 2
      update_config: { parallelism: 1, order: start-first, delay: 10s }
      resources:
        limits: { cpus: "2", memory: 2G }
    networks: [contexta-public, contexta-internal]
    ports: ["443:443", "80:80"]
    secrets: [mtls-key, mtls-cert]

  data-plane:
    image: registry.contexta.dev/data-plane:1.0.0
    deploy:
      replicas: 2
      resources: { limits: { cpus: "8", memory: 6G } }
    networks: [contexta-internal]

  python-api:
    image: registry.contexta.dev/contexta:1.0.0
    command: api
    deploy:
      replicas: 3
      resources: { limits: { cpus: "4", memory: 4G } }
    networks: [contexta-internal]
    secrets: [contexta-env]

  python-worker-extraction:
    image: registry.contexta.dev/contexta:1.0.0
    command: worker
    environment:
      CONTEXTA_WORKER_QUEUES: extraction,embedding
      CONTEXTA_WORKER_CONCURRENCY: "8"
    deploy:
      replicas: 2
    networks: [contexta-internal]

  python-worker-maintenance:
    image: registry.contexta.dev/contexta:1.0.0
    command: worker
    environment:
      CONTEXTA_WORKER_QUEUES: maintenance
      CONTEXTA_WORKER_CONCURRENCY: "4"
    deploy:
      replicas: 1
    networks: [contexta-internal]

  python-beat:
    image: registry.contexta.dev/contexta:1.0.0
    command: beat
    deploy: { replicas: 1 }
    networks: [contexta-internal]

  aggregator:
    image: registry.contexta.dev/aggregator:1.0.0
    deploy:
      replicas: 2     # leader-elected via Redlock; 2 for failover
    networks: [contexta-internal]

networks:
  contexta-public: { external: true }
  contexta-internal: { external: true }

secrets:
  contexta-env: { external: true }
  mtls-key: { external: true }
  mtls-cert: { external: true }
```

Deploy: `docker stack deploy -c stack.prod.yml contexta`.

## Region expansion plan

| Month | Action | Cost delta |
|---|---|---|
| 0 | EU-FSN1 launch (described above) | Baseline $615/mo |
| 4 | Add US edge gateway in `us-east-1` (AWS t3.small × 2) for US customer latency. Round-trips still cross to FSN1. | +$40/mo |
| 9 | Add US primary (AWS bare metal `m5d.4xlarge` for Postgres, app on Fargate) when US MRR > $10k/mo | +$1,800/mo, offset by US revenue |
| 12 | Add AP-SG edge gateway for SG/JP/AU customers | +$30/mo |
| 18 | Add AP primary if AP MRR > $5k/mo | +$1,500/mo |

Each new region runs the **same stack file** with region-specific environment variables. Postgres replicates from the writeable region only; cross-region writes go through the routing layer.


## Data isolation enforcement

The customer's question was specifically about isolating compute from storage on dedicated machines. Here's how that lands:

| Concern | Implementation |
|---|---|
| Postgres on its own physical box | Yes. AX52 dedicated, no other workloads. |
| Redis on its own VM | Yes. CCX23 dedicated. |
| API tier separated from worker tier | Yes. Different VMs, different machine classes. |
| Worker tier separated from data plane | Yes. Workers on Python (LLM-bound), data plane on Go (DB-bound). |
| Edge gateway separated from upstreams | Yes. Only gateway has a public IP. |
| Aggregator separated from API | Yes. Singleton on its own small VM. |
| Postgres replica in a different region | Yes. HEL1, ~600 km from FSN1, cross-region private link. |
| Backups separated from primary | Yes. Hetzner Storage Box on different physical infrastructure. |

This satisfies "data plane lives on a dedicated machine, compute on another, vector on another" without going overboard. Adding more separation (e.g., per-component bare metal) would 5x the cost without buying real isolation.

## Failure scenarios

What happens when each component dies:

| Failure | Impact | Recovery |
|---|---|---|
| Single API container | None — Swarm reschedules in seconds, LB routes around | Auto |
| All API containers | Dashboard server actions fail; agents using control-plane endpoints fail | Restart in <30s |
| Single data plane container | None — LB routes around | Auto |
| All data plane containers | Customer agents fail observation/retrieval | Gateway 503; agents retry |
| Single worker | Tasks reroute to other workers; Celery acks_late prevents loss | Auto |
| All workers | Extraction queue grows; agents see 202 but no memories created until workers come back | Up to several minutes acceptable; queue depth alerts page on-call |
| Postgres primary | All writes fail; reads continue from replica | Failover replica (manual at v1, ~15 min RTO) |
| Postgres replica | Read path falls back to primary; writes unaffected; backup risk if extended | Spin up new replica from base backup; ~30 min |
| Redis primary | Rate limiting and quota enforcement degraded; gateway short-circuits to "allow with warning"; meter events buffered to local file | Sentinel promotes replica; ~30s |
| Edge gateway | Cloudflare returns 503 if all instances dead | Auto-restart; if persistent, manual incident |
| Cloudflare outage | DNS still works (we use multiple anycast providers); origin still reachable via direct IP | Page on-call |
| Hetzner FSN1 outage | Full regional outage — manual failover to HEL1 (Postgres replica becomes primary) | RTO 30–60 min |

Detailed playbooks are in [13-operations-and-security.md](./13-operations-and-security.md).

## Secrets management

- All secrets in Docker Swarm Secrets / k8s Secrets (encrypted at rest in the orchestrator's KV store).
- Stripe keys, OpenAI keys, JWT signing key, DB password.
- Customer BYOK keys are encrypted at rest in Postgres using AES-256-GCM with a tenant-derived key. The decryption key is held in HashiCorp Vault (single dedicated VM at v1, managed Vault later).
- We rotate signing keys quarterly. Documented in [13](./13-operations-and-security.md).

## Monitoring stack

| Concern | Tool |
|---|---|
| Logs | Vector or Promtail → Grafana Loki on a dedicated VM, retention 14 days hot + 90 days S3 |
| Metrics | Prometheus on dedicated VM, scrape every 15s, retention 30 days |
| Traces | Honeycomb (paid, ~$100/mo) or self-hosted Tempo |
| Dashboards | Grafana on the same VM as Prometheus |
| Alerts | Grafana Alerting → Slack + PagerDuty |
| Uptime checks | Better Stack or self-hosted Uptime Kuma |
| Error tracking | Sentry (free tier sufficient at launch) |

Cost: ~$50/mo extra at launch.

## Capacity planning

The current topology supports:
- 1,000 active organizations
- 50M total active memories (across all tenants)
- 100k retrievals/min sustained
- 5k observations/min sustained
- 99.9% uptime SLA

We re-evaluate at:
- 80% of any capacity dimension.
- 50% of Postgres RAM (HNSW headroom).
- 80% of any subscription tier customer count vs original projection.

When triggered, we double the relevant tier of compute or move to a larger machine class. All upgrades are non-disruptive (rolling on the API/worker tier; a maintenance window for Postgres upgrade).

## Why this scales

The topology is deliberately conservative. We could go cheaper (single VM running everything) but we'd hit Postgres lock contention or kernel-level resource starvation by month 3. We could go more expensive (managed Kubernetes, AWS RDS, ElastiCache) but we'd burn 4-5x the cost.

The chosen middle path:
- Cheap enough that Year 1 infra cost is < 2% of MRR.
- Robust enough that no single failure is catastrophic.
- Simple enough that one engineer can run it.
- Migratable — every container is portable. We can move FSN1 → AWS or HEL1 → GCP in a week if needed.
