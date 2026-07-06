# 17 — Security and Abuse Protection

This document covers everything that protects contexta from being weaponized: spammers filling the database with junk, attackers brute-forcing API keys, customers DoSing each other (cross-tenant), and external bots probing for vulnerabilities.

The core risk to address: *"so that our DB won't get spammed."* That's the headline of this doc. Plus tenant isolation hardening, abuse detection, and the security baseline that comes with any SaaS that holds customer data.

## Decisions of record

1. **No data ingestion without authentication.** Every write requires a valid API key.
2. **Per-key rate limit + per-tenant quota at the edge gateway.** Both must pass.
3. **Per-tenant Postgres write quota at the data plane.** Defense in depth: even if rate limit is bypassed, the data plane caps writes per tenant per minute.
4. **Sensitive data scanning is mandatory and non-bypassable.** No tenant can opt out.
5. **All API keys hashed at rest (SHA-256). Plaintext shown once.**
6. **Internal services on private network only.** Only the edge gateway has a public IP.
7. **Audit log is append-only.** No UPDATE or DELETE statements ever run against `audit_log` (enforced by RLS + DBA review).


## Threat model

| Threat actor | Capability | Goal | Mitigation |
|---|---|---|---|
| Random internet | None | Probe for vulns, DDoS | Cloudflare WAF, edge gateway, no public Postgres/Redis |
| Compromised customer key | Valid API key | Spam DB, exfiltrate one tenant's data | Per-key rate limit, per-tenant quota, anomaly detection, customer-rotatable keys |
| Malicious tenant | Their own valid key | Try to read other tenants' data | Tenant isolation (repository, gateway, RLS) |
| Curious customer | Browser at app.contexta.dev | Try to escalate privileges in dashboard | Server actions, no client-trust, RBAC |
| Insider (operator) | Production DB access | Exfiltrate customer data | Two-person approval for DB super-user actions, audit log of every operator query |
| Compromised dependency | npm/pip supply chain | Backdoor inserted via SDK update | Signed releases, SBOM, version pinning, weekly audit |
| Bot scraping signups | Cloud IP | Fill the auth tables | hCaptcha on signup, email verification, rate-limit signups per IP |
| Stripe webhook spoof | Knowledge of webhook URL | Trigger plan upgrade for free | Stripe signature verification mandatory |
| API key brute force | None | Guess valid mk_live tokens | 32-byte tokens (effective 256 bits entropy), per-IP rate limit on bearer-rejection 401s |

## Database spam protection (the headline)

Concrete attack: an attacker obtains a valid API key (theirs or a leaked one), then writes 1B observations in a week. They blow out our storage costs, slow down everyone else's retrieval, and drown the queue.

### Layered defense

```
Customer Request
       │
       ▼
[ Cloudflare ]                  L1: DDoS, WAF, bot mitigation
       │
       ▼
[ Edge Gateway ]                L2: per-key rate limit (token bucket in Redis)
       │                        L3: per-tenant quota check (Redis counter)
       │                        L4: bearer auth required (or 401)
       ▼
[ Data Plane ]                  L5: per-tenant write rate cap (defense in depth)
       │                        L6: per-tenant DB connection pool cap
       │                        L7: sensitive data scan
       │                        L8: payload size cap (1 MB)
       ▼
[ Postgres ]                    L9: row count check on plan limits
       │                        L10: disk space alarm
       ▼
[ Workers ]                     L11: queue depth alarm + per-tenant fairness
                                L12: LLM cost cap (BYOK protects us anyway)
```

### Layer-by-layer

**L1 (Cloudflare):** Rate-limit by IP — 100 req/sec per IP for unauthenticated traffic. Block known bot ranges. WAF rules for OWASP Top 10.

**L2 (per-key rate limit):** Token bucket. Tier-defined caps (10/50/250/1000 RPS). Burst = 2× steady. Returns 429 with `Retry-After`.

**L3 (per-tenant quota):** Redis counter `quota:obs:<tenant>:<period>`. Hard cap on returns 429; soft cap allows with overage tracking.

**L4 (bearer auth):** No bearer → 401. Invalid bearer → 401. Per-IP, we rate-limit 401 responses to 10/min to slow brute-force. Repeated 401s from the same IP get IP-banned for 1 hour after 100 fails in 5 min.

**L5 (per-tenant write rate cap):** Even if L2/L3 are misconfigured, the data plane has its own cap: 200 writes/sec per tenant on the hot path, 50 writes/sec on the slow path (sessions, policies). Returns 503 with `Retry-After` if exceeded.

**L6 (per-tenant connection cap):** PgBouncer is configured with `default_pool_size=100` total. Per-tenant we cap at 20 concurrent connections via a Redis semaphore in the data plane. One tenant cannot starve everyone else.

**L7 (sensitive data scan):** Mandatory. The redactor is on the hot path — observation never goes to extraction without this pass. It also serves as a coarse spam detector: payloads with > 50% redacted bytes are auto-rejected with `error.code = "PAYLOAD_TOO_RISKY"` (since they're either secrets or junk).

**L8 (payload size):** 1 MB hard cap on observation body. 50 observations max per batch.

**L9 (plan-limit row count):** A daily `pg_partition` row count check per tenant. If a tenant exceeds 110% of plan limit, hard cap engages immediately regardless of dashboard setting (defense against soft-cap bypass).

**L10 (disk):** 70% warn, 85% page, 95% read-only.

**L11 (queue depth):** If extraction queue depth > 100k for a single tenant, that tenant's queue gets de-prioritized (Celery routing pulls from "fair queue" first, then their queue). Other tenants see normal latency.

**L12 (LLM cost cap):** With BYOK as default, the customer's own LLM bill is the natural cost cap. For Managed-LLM, we cap at the bundle the customer paid for. They can't blow past it without a paid bump.

### Soft signals (anomaly detection)

Beyond hard caps, we watch for patterns that suggest abuse without exceeding limits:

| Signal | Threshold | Action |
|---|---|---|
| Unique observation hashes / total observations | < 0.05 | Flag: same payload spammed |
| 95th percentile observation size | > 500 KB | Flag: suspicious |
| Observation rate spike | > 10x 7-day avg | Flag: investigate |
| Geo distribution of API key usage | > 5 distinct countries / hour | Flag: possible key share/leak |
| Failed auth attempts per IP | > 50 / hour | IP ban |
| Failed schema validation rate | > 30% | Flag: customer integration broken or attacking |

Flagged tenants are surfaced to internal Slack `#abuse-watch` (not paged). On-call investigates within 1 business day. We never auto-suspend without human review unless the threshold is severe (e.g., 1000 failed auths/hour from one IP = auto-ban).


## Tenant isolation hardening

The repo already has `TenantScopedRepository` enforcing `WHERE organization_id = $tenant`. We add three more layers:

### 1. Postgres row-level security (RLS)

Enable on every domain table:

```sql
ALTER TABLE memory_record ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_record FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON memory_record
  USING (organization_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (organization_id = current_setting('app.tenant_id', true)::uuid);
```

The `app.tenant_id` setting is set per-transaction via `SET LOCAL app.tenant_id = '...'` at session start. Even if application code forgets the WHERE clause, RLS catches it.

`FORCE` ensures the policy applies even to table owners.

### 2. Connection-level tenant binding

Every async DB session begins with:

```python
async with engine.begin() as conn:
    await conn.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))
    # ... rest of transaction
```

The Go data plane does the same via `pgx.ExecParams`. PgBouncer in transaction mode preserves this within the transaction; afterwards the connection is reset.

### 3. Cross-tenant read tests in CI

A property test runs in CI:
- Create two tenants with random data.
- For every list/get endpoint, attempt to access tenant B's data with tenant A's auth.
- Assert all attempts return 403/404 with no data leakage in error messages.

If any test fails, the build fails. This catches regressions where someone forgets a WHERE clause.

## API key security

### Token format

```
mk_live_<32 url-safe bytes>
```

- 32 bytes = 256 bits of entropy. Brute force is computationally infeasible.
- Prefix `mk_live_` enables credential scanning tools (GitHub Push Protection, GitLeaks) to detect leaked keys.
- Test keys use `mk_test_` prefix.

### At rest

- Only the SHA-256 hash is stored.
- Plaintext shown ONCE in the create-modal in the dashboard or once via the CLI on creation.
- Lookup at gateway: `SELECT ... FROM api_key WHERE token_hash = $1`.
- Database column `token_hash` has UNIQUE constraint.

### In transit

- TLS 1.3 enforced on all external connections (Cloudflare → gateway).
- Internal service-to-service mTLS (rolling out by month 3).
- Bearer never logged. Logging middleware redacts `Authorization` header at all levels.

### Rotation and revocation

- Rotate (POST /v1/keys/{id}/rotate): new token issued, old valid for 24h grace.
- Revoke (DELETE /v1/keys/{id}): old token instantly invalid (Redis cache invalidated within 60s, or instant via pub-sub).
- Customer-initiated only at v1. contexta operators do not revoke customer keys without ticket + customer confirmation.

### Leak monitoring

- We register the `mk_live_` and `mk_test_` prefixes with GitHub Secret Scanning.
- When GitHub detects a leaked key, they notify us. We auto-revoke and email the customer within 5 minutes.
- We also run a daily scrape of public Pastebin / SearchCode for the prefixes (third-party service, ~$50/mo).

## Authentication of dashboard users

- Auth.js / NextAuth with Argon2id password hashing.
- Email verification mandatory before paid actions.
- Rate-limited sign-in: 5 attempts per email per hour, then forced cooldown.
- IP-based rate limit on signup endpoint: 10/hour per IP.
- hCaptcha on signup form (rotates from Hobby tier when bot signups detected).
- Session JWT signed with HS256; signing key rotated quarterly.
- Session lifetime: 7 days sliding, 30 days absolute.
- Logout invalidates the JWT in a Redis denylist (TTL = remaining JWT lifetime).
- Optional MFA via TOTP (post-launch).

## Network security

### Public surface (only)

| Service | Public IP | Port |
|---|---|---|
| Edge gateway | Yes | 443 (HTTPS), 80 (redirect to 443) |
| Dashboard (Vercel or self-hosted) | Yes | 443 |

### Private only

Postgres, Redis, Python API, Go data plane, workers, aggregator, monitoring stack, log aggregator. None have public IPs.

### Firewall

- Hetzner Cloud Firewall: deny inbound except from internal vSwitch.
- Edge gateway box: only 80/443 inbound from Cloudflare IP ranges. Direct origin access denied (Cloudflare has a firewall rule, plus origin firewall).
- SSH: only from operator IPs, key-based auth, MFA on the bastion host.
- Cloudflare Authenticated Origin Pulls so the origin only accepts requests from Cloudflare.

### DDoS

- Cloudflare provides L3/L4/L7 protection.
- Edge gateway has an internal rate limit per IP (in addition to per-key) for unauthenticated traffic — 100 req/s per IP.
- Sustained DDoS (> 1 Gbps) triggers Cloudflare Under Attack mode (manual toggle, ~5 min RTO).

## Audit log integrity

The `audit_log` table is append-only by policy:

- No application code path issues UPDATE or DELETE on `audit_log`. (Reviewed in code search at every PR; gitleaks-style hook fails commits that include such SQL.)
- Postgres RLS policy explicitly disallows UPDATE and DELETE.
- DBA-level deletes (for retention rotation) are logged in a meta-audit table that's also append-only.

We ship every audit row to a separate write-only S3 bucket nightly. Even if the DB is compromised, the audit trail is recoverable.

## Sensitive data: defense in depth

The Python `sensitive_filter.py` catches passwords, API keys, JWTs, payment cards, OTPs, session cookies. Three layers:

1. **Primary scan at gateway:** redact obvious patterns before observation enters the queue.
2. **Secondary scan at extraction:** LLM-extracted memories are re-scanned. If found, memory is discarded.
3. **Tertiary scan at storage (planned):** before writing to `memory_record`, last-chance scan. If found, write a flagged audit row and discard.

The redaction catalog is versioned in `redaction-catalog.yaml`. Both Python and Go ports use the same catalog. CI tests both implementations against the same fixture corpus.

We will never train an ML model on customer data without explicit consent. The redaction is regex-based and deterministic.


## Supply chain security

### Dependencies

- Pip lock file (`uv.lock` or `pip-tools` `requirements.lock`) committed.
- npm lock file (`pnpm-lock.yaml`) committed.
- Go modules with `go.sum` committed.
- `pip-audit`, `npm audit`, `govulncheck` in CI on every PR.
- Dependabot weekly PRs for non-major bumps; manual review for major.

### Container images

- Distroless base for Go services.
- Slim Python base.
- `trivy` scan on every image build. Block on HIGH or CRITICAL.
- Image signing via Sigstore (cosign). Production deploy verifies signature.

### CI/CD

- GitHub Actions with OIDC to deploy targets (no long-lived secrets).
- Deploy approvals required for production from a different person than the PR author (when team > 1).
- Branch protection on `main`: require 1 review, status checks pass, no force push.

## Customer-data privacy

| Data | What we do |
|---|---|
| Memory content | Stored, processed, never sold or shared. Encrypted at rest via LUKS. |
| End-user user_id | Stored as opaque UUID. We don't know who they are. |
| Email (account) | Stored, used only for transactional emails. Never marketed (unless customer opts in). |
| BYOK LLM key | Encrypted with tenant-scoped DEK; KEK in Vault; never logged; never sent anywhere except the LLM provider. |
| API key | Hashed only. Plaintext shown once. |
| Stripe customer | Stored ID only. Card data never touches our infra. |
| Payment events | Stored as Stripe Customer ID + invoice IDs. |
| Logs | Sanitized: bearer tokens, passwords, BYOK keys redacted at write time. |
| Backups | Encrypted at rest. Stored on Hetzner Storage Box separate from primary. |
| Internal access | Operator queries against customer data require ticket + audit log entry. Each entry visible to customer. |

## Right to be forgotten (GDPR / CCPA)

| Action | Customer-initiated | Operator-initiated |
|---|---|---|
| Export tenant data | Self-serve via dashboard, JSONL format, signed URL valid 24h | Manual via support ticket |
| Delete tenant data | Self-serve via dashboard "Delete org" → 90-day soft delete → hard delete | Same |
| Delete a specific user_id's memories | DELETE /v1/users/{user_id}/memories endpoint, irreversible, cascade | Same |
| Pause processing | "Suspend org" toggle, all writes return 403 | Same |

We commit to:
- Soft delete (rows still in DB) within 1 hour of customer request.
- Hard delete (rows gone) within 30 days.
- Audit log of the deletion retained per legal hold requirements (7 years for billing-related, 90 days otherwise).

## Compliance posture

- **GDPR** — Yes, EU primary region, DPA template, data export, right to delete, breach notification SLA.
- **CCPA** — Yes, equivalent to GDPR for our scope.
- **SOC 2 Type I** — Auditor engaged month 9, report month 12.
- **SOC 2 Type II** — Observation window starts month 12, report month 18.
- **HIPAA / BAA** — Enterprise tier only, post-launch, requires single-tenant infra.
- **ISO 27001** — Post-Series A.
- **PCI** — Out of scope. Stripe handles card data; we never touch it.

## Security incident response

Linked to [13-operations-and-security.md](./13-operations-and-security.md). Severity ladder:

| Sev | Examples | Public disclosure |
|---|---|---|
| Sev 1 | Confirmed cross-tenant exposure, customer data exfiltrated, ransomware | Within 24 hours to affected customers and any required regulator |
| Sev 2 | Suspected exposure under investigation, dependency CVE actively being attacked | Within 72 hours |
| Sev 3 | Internal-only event (no customer data), patched dependency CVE | No public disclosure required |
| Sev 4 | Cosmetic security finding | Tracked internally |

GDPR breach notification: within 72 hours to the relevant Data Protection Authority and affected customers, where applicable.

## What we explicitly defer

- Web Application Firewall custom rules beyond Cloudflare defaults (defer to month 3).
- Bug bounty program (defer to month 12, post-public-launch, after 1 external pentest).
- Customer-managed encryption keys (Enterprise feature, post-launch).
- Per-region data residency beyond EU/US (after AP region launches).
- Third-party penetration test (one before public launch, then annual).
- Hardware security keys (FIDO2) for operator MFA (defer to month 6, TOTP sufficient at launch).
