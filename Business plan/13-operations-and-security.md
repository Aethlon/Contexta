# 13 — Operations and Security

This document is the runbook for operating contexta in production. Every section is something an on-call engineer could need at 3am.

## Decisions of record

1. **One on-call engineer at a time.** No "primary + secondary" until headcount supports it. The on-call rotates weekly.
2. **PagerDuty for paging, Slack for low-severity alerts.**
3. **Severity 1 (full outage) target: ack within 5 min, mitigation within 30 min, restore within 60 min.**
4. **Severity 2 (degraded service) target: ack within 15 min, mitigation within 2 hours.**
5. **Public status page from day one.** `status.contexta.dev` powered by Better Stack.
6. **No customer-impacting incident is silently fixed.** Every Sev1/Sev2 gets a public post-mortem within 5 business days.


## Observability requirements (every service)

Every service must implement:

1. **`/healthz`** — process is alive (returns 200 unconditionally if running).
2. **`/readyz`** — process is ready to serve traffic (checks DB, Redis, downstreams). Returns 503 during boot or shutdown.
3. **`/metrics`** — Prometheus scrape endpoint with at minimum:
   - `http_requests_total{endpoint, method, status}` (counter)
   - `http_request_duration_seconds{endpoint, method}` (histogram)
   - `CONTEXTA_queue_depth{queue}` (gauge, workers/aggregator)
   - `CONTEXTA_db_pool_in_use` (gauge)
   - `CONTEXTA_redis_ops_total{op}` (counter)
   - `CONTEXTA_llm_calls_total{provider, model, status}` (counter)
   - `CONTEXTA_llm_latency_seconds{provider, model}` (histogram)
   - `CONTEXTA_active_memories{tenant_id}` (gauge, scraped infrequently)
4. **Structured logs** — JSON one line per event, fields: `ts`, `level`, `msg`, `request_id`, `tenant_id`, `actor_id`, `endpoint`, `service`, `region`, plus event-specific fields.
5. **OpenTelemetry traces** — every external request creates a root span; each downstream call is a child.
6. **Sentry exception capture** for uncaught exceptions, with `request_id` and `tenant_id` tags.

## Alert taxonomy

Alerts fall into 4 buckets:

| Sev | Examples | Page? | Response time |
|---|---|---|---|
| Sev 1 | API tier 5xx > 5% for 2 min, all data plane unhealthy, Postgres primary down | Yes | 5 min ack |
| Sev 2 | API tier 5xx > 1% for 5 min, queue depth > 10k, replica lag > 60s, p95 latency 2x baseline | Yes | 15 min ack |
| Sev 3 | Cert expiring in 7 days, disk usage > 80%, single worker crash-looping | Slack | 1 business day |
| Sev 4 | Daily report of slow queries, weekly backup verification, dependency vuln found | Slack | weekly review |

## Runbooks

Each runbook is a markdown file in `Business plan/runbooks/<scenario>.md`. The on-call engineer reads it from the alert link. Every runbook has the same shape:

```
# Runbook: <scenario name>
Severity: 1 / 2
Owner: on-call

## Symptoms
What you see in dashboards / what alerts fire.

## Diagnosis
Commands to run, what their output means.

## Mitigation
The shortest path to restore service.

## Recovery
Bringing the system back to full health.

## Post-incident
Required artifacts: post-mortem, timeline, customer comms.
```

Required runbooks at v1 launch:

- `postgres-primary-down.md`
- `postgres-replica-down.md`
- `postgres-replica-lag.md`
- `redis-primary-down.md`
- `extraction-queue-overflow.md`
- `gateway-5xx-spike.md`
- `data-plane-5xx-spike.md`
- `worker-stuck.md`
- `cert-expiring.md`
- `disk-full.md`
- `stripe-webhook-failure.md`
- `cloudflare-bypass-required.md`
- `dns-failure.md`
- `region-failover.md`

## Backups and recovery

### Automated
- WAL shipping every 5 minutes to Hetzner Storage Box.
- Daily `pg_basebackup` at 03:00 UTC, retained 30 days.
- Weekly verification: a CI job downloads the latest base backup, restores into a sandbox VM, runs `SELECT count(*) FROM memory_record`, decommissions.

### Manual recovery
Documented in `runbooks/postgres-restore.md`. Test quarterly during a dedicated game-day exercise.

### RPO/RTO commitments
- RPO: 5 minutes (max data loss in worst case).
- RTO Sev 1 partial outage: 30 minutes.
- RTO full region outage with failover to HEL1: 60 minutes.
- RTO full restore from cold backup: 4 hours.

## Security baseline

### Authentication and authorization
- All admin actions require MFA on the operator's account (Auth.js + TOTP).
- API keys are SHA-256 hashed at rest. The plaintext is shown once at creation.
- Internal service-to-service auth via mTLS (rolled out by month 3).
- Customer JWTs signed with rotating keys. Old keys remain valid until expiry; new tokens use the new key.

### Encryption
- TLS 1.3 enforced on all external traffic; TLS 1.2 minimum.
- Postgres data at rest: LUKS full-disk encryption on Hetzner volumes.
- Redis: TLS in transit, in-memory only (no persistence of secrets).
- S3 archive: SSE-S3 (AES-256) on Hetzner Storage Box.
- BYOK customer LLM keys: AES-256-GCM with a tenant-derived data encryption key, KEK in HashiCorp Vault.

### Secrets management
- Docker Swarm Secrets / k8s Secrets store all sensitive env vars.
- HashiCorp Vault holds:
  - JWT signing key (rotated quarterly).
  - Customer BYOK key encryption key (KEK).
  - Stripe key (read by control plane only).
  - Postgres super-user password (rotated semi-annually).
- `.env` files never committed to git (enforced by `.gitignore` and `gitleaks` pre-commit hook).

### Network
- Only edge gateway and dashboard have public IPs.
- All other services on private VLAN.
- Cloudflare WAF rules block known bot patterns and OWASP Top 10 attacks.
- Rate limiting at gateway: 10/50/250/1000 RPS per API key by plan.
- Geo-blocking on Cloudflare for high-abuse regions when needed (configurable in dashboard for Enterprise).

### Audit
- Every admin action (key revoke, plan change, data export, force-delete) writes to `audit_log`.
- Audit log retained per plan (30 days Hobby → unlimited Enterprise).
- Audit log is append-only at the table level. Hard delete only via DBA with two-person approval.

### Vulnerability management
- `pip-audit` and `npm audit` weekly.
- `trivy` scans on every Docker image build.
- `gitleaks` pre-commit and post-merge hooks.
- Weekly scan of all customer-facing surfaces with OWASP ZAP.
- Quarterly external pentest (post-launch).

### Compliance roadmap
- **GDPR** — covered by EU primary region, customer data export endpoint, DPO contact, 30-day deletion SLA. Documented in privacy policy.
- **SOC 2 Type I** — auditor engaged month 9, report by month 12.
- **SOC 2 Type II** — observation window starts month 12, report by month 18.
- **HIPAA + BAA** — Enterprise tier only, opt-in feature, requires separate single-tenant infrastructure (no PHI in shared tier).
- **ISO 27001** — post-Series A.

## Incident response

### Communication channels
- **Public status page**: `status.contexta.dev` — auto-updated by uptime checks.
- **#incidents Slack channel** — internal coordination.
- **Customer Slack/Discord channels** — paying customers see honest "we're investigating" updates within 15 min of Sev 1.
- **Email blast** — only for confirmed customer-impacting incidents > 1 hour.
- **Post-mortem** — published to `https://contexta.dev/post-mortems/YYYY-MM-DD-summary` within 5 business days.

### Roles during an incident
- **Incident Commander (IC)** — runs the bridge call, decides escalations.
- **Operations** — executes runbook, mitigates.
- **Communications** — writes status page updates, sends customer messages.
- **Scribe** — keeps a timeline.

In a 2-person company, IC + Operations is one person; Comms is the other; Scribe is anyone who has hands free.

### Game days
- Quarterly Chaos Day: kill a random container, fail over Postgres, drain a worker queue. Document what broke.
- Annual full-region failover drill.


## On-call rotation

Week-long rotations. The on-call:
- Carries the PagerDuty number.
- Watches Slack #alerts.
- Owns Sev 1/2 acknowledgement.
- Has a 5-minute response SLA during business hours and 15 min off-hours.
- Is paid an on-call stipend (will be defined in [14-roadmap-and-finances.md](./14-roadmap-and-finances.md)).

Hand-off Friday at 17:00 local. Outgoing on-call sends a short brief: open issues, recent changes, anything brittle.

## Change management

### Deploy windows
- Anytime for the API and data plane (rolling deploys, no downtime).
- Maintenance windows (03:00–05:00 UTC, Tue/Thu) for Postgres upgrades or breaking migrations.
- Frozen deploys during incident response and 7 days before major holidays.

### Pre-deploy checks
- All tests green.
- Migration plan reviewed (if any DDL).
- Deploy lead acknowledges in #deploys Slack.
- Status page banner ready (drafted, not published).

### Rollback policy
- Every release has a one-command rollback (`docker stack rollback contexta`).
- DB migrations must be reversible. If the migration is irreversible (rare), it ships with a backwards-compatible deploy first, then the irreversible step in a follow-up.
- Rollback decision: if customer-impacting issue isn't resolved in 10 min, roll back, fix, redeploy.

## Disaster recovery

| Scenario | Recovery |
|---|---|
| Hetzner FSN1 region offline | Promote HEL1 replica, repoint DNS, customers may see ~1 hour outage. |
| Both EU regions offline | Bring up emergency stack on AWS Frankfurt from latest base backup (4 hours). |
| Postgres data corruption | Stop writes, restore from latest WAL-shipped backup point (5-min RPO), replay anything in flight. |
| Encryption key loss | Vault has 5-of-9 Shamir key shards distributed to founders + advisor + cold storage. |
| Account compromise (operator) | Revoke session, rotate signing keys, audit recent actions, notify customers if data accessed. |
| API key leak (customer) | Customer rotates via dashboard. We can force-revoke if abuse detected. |
| Total operator wipe (entire team incapacitated) | Continuity plan: separate operator (advisor) has read-only Postgres + Vault access; can run a maintenance-only mode. |

## Customer data lifecycle

| Event | Effect |
|---|---|
| Customer signs up | `account` row created |
| Customer creates org | `organization` row + default `project` row |
| Customer first observation | Memory rows accumulate |
| Customer cancels | Subscription `cancelled` in Stripe; data retained 30 days; export emailed |
| 30-day grace ends | Org marked `deleted`; data soft-deleted (kept 60 more days for recovery) |
| 90-day soft-delete ends | Hard delete: rows removed from Postgres, embeddings deleted, audit log retained for legal hold |
| Customer requests immediate delete | Hard delete within 30 days, confirmation email sent |

## Security incident classification

| Class | Examples | Disclosure SLA |
|---|---|---|
| 1 | Confirmed cross-tenant data exposure, ransomware, credential theft | 24h to affected customers + regulators if applicable |
| 2 | Suspected exposure under investigation, dependency vuln in our stack | 72h to affected customers |
| 3 | Internal-only (no customer data) | Documented internally, no external comms |

GDPR breach reporting (when applicable) within 72 hours to the relevant DPA. Documented in DPA template.

## Access controls

| Resource | Who has access |
|---|---|
| Production Postgres super-user | Founders only, MFA + jump host |
| Production Redis admin | Founders + on-call (read), founders only (write) |
| Stripe live mode | Founders only |
| HashiCorp Vault root | Founders only, MFA |
| Cloudflare account | Founders only |
| Hetzner Robot account | Founders only, MFA |
| Production deploy | Founders + senior engineers, gated by GitHub team |
| Customer org data (support read-only) | Founders + on-call (with audit log entry per access) |

Every access to a customer's tenant data by an operator writes an audit log entry visible to the customer (and to compliance auditors).

## Logging conventions

- All logs in JSON.
- All logs include `request_id`, `tenant_id`, `actor_id` when applicable.
- All logs go to stdout; orchestrator collects via Promtail/Vector to Loki.
- Retention: 14 days hot in Loki, 90 days cold in S3-compatible storage.
- Customer requests for their own log data are fulfilled via export within 7 business days.

## Privacy of telemetry

- We do not log message content beyond first 200 chars in development.
- We do not log API keys, passwords, JWTs, or BYOK LLM keys (sensitive_filter scrubs them on the way in).
- We do not export customer data to any third party except: Stripe (billing), Postmark (email), Honeycomb (traces, sanitized), Sentry (errors, sanitized).

The full third-party processor list is on the privacy page and updated when changed.
