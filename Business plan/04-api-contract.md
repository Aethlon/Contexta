# 04 — API Contract (internal wire format)

This is the internal wire contract for contexta. **The SDK is the public product** ([18-sdk-first-product-contract.md](./18-sdk-first-product-contract.md)); this document specifies the HTTP endpoints the SDK calls underneath. Customers can use the HTTP API directly as a fallback when an SDK is unavailable for their language.

The contract is versioned at `/v1/`. Breaking changes get `/v2/` and old version supported for 12 months minimum.

## Base URL

```
https://api.contexta.dev/v1
```

Per-region:

- `https://api.contexta.dev/v1` — autoroute by anycast (default)
- `https://eu.api.contexta.dev/v1` — EU pin
- `https://us.api.contexta.dev/v1` — US pin (when available)

## Authentication

Every request must include either:

```
Authorization: Bearer mk_live_<32 url-safe bytes>
```

or, in the dashboard's server actions only:

```
Authorization: contexta <session_jwt>
```

API keys are scoped per project and have an explicit scope set:

| Scope | Permits |
|---|---|
| `observations:write` | POST /observations |
| `retrieval:read` | POST /retrieve, GET /context |
| `memories:read` | GET /memories/* |
| `memories:write` | POST/PATCH/DELETE on /memories/* (pin/unpin/archive/restore/delete) |
| `policies:write` | Policy CRUD |
| `schemas:write` | Custom schema CRUD |
| `audit:read` | Audit log query |
| `*` | All of the above |

The default scope set on a new key is `observations:write,retrieval:read,memories:read`. The dashboard has checkboxes to expand.

Tokens are shown once at creation and never displayed again. Customers see the prefix (first 16 chars) for identification.

## Read vs write classification (for billing)

Every endpoint is classified for the meter. This is what the customer is charged for.

| Endpoint | Method | Class | Counts as |
|---|---|---|---|
| `/v1/observations` | POST | **WRITE** | 1 observation |
| `/v1/observations/batch` | POST | **WRITE** | N observations (N = batch size) |
| `/v1/retrieve` | POST | **READ** | 1 retrieval; +1 rerank if `rerank=true` |
| `/v1/context` | GET | **READ** | 1 retrieval (context bundle counts as one) |
| `/v1/memories/{id}` | GET | **READ** | 1 read |
| `/v1/memories/{id}/explain` | GET | **READ** | 1 read |
| `/v1/memories/{id}/pin` | POST | **WRITE** | 1 lifecycle op |
| `/v1/memories/{id}/unpin` | POST | **WRITE** | 1 lifecycle op |
| `/v1/memories/{id}/archive` | POST | **WRITE** | 1 lifecycle op |
| `/v1/memories/{id}/restore` | POST | **WRITE** | 1 lifecycle op |
| `/v1/memories/{id}` | DELETE | **WRITE** | 1 lifecycle op |
| `/v1/memories/timeline/{user_id}` | GET | **READ** | 1 read |
| `/v1/sessions` | POST | **WRITE** | 1 session start |
| `/v1/sessions/{id}/end` | POST | **WRITE** | 1 session end (no overhead, triggers epilogue) |
| `/v1/sessions/inspect/{user_id}` | GET | **READ** | 1 read |
| `/v1/policies` | GET | READ | not metered |
| `/v1/policies` | POST | WRITE | not metered |
| `/v1/schemas` | GET | READ | not metered |
| `/v1/schemas` | POST | WRITE | not metered |
| `/v1/keys` | * | * | not metered |
| `/v1/usage`, `/v1/audit`, `/v1/projects`, `/v1/billing/*` | * | * | not metered |
| `/healthz`, `/readyz`, `/metrics` | GET | infra | not metered |

**Lifecycle ops, sessions, policies, schemas, projects, key ops, billing, and audit are NOT metered against the customer's quota.** This is intentional. Customers should never feel taxed for managing their own data.

## Standard request envelope

All POST/PATCH bodies are JSON. Required headers:

```
Authorization: Bearer mk_live_...
Content-Type: application/json
Idempotency-Key: <uuid>      (recommended for writes)
X-contexta-User-Id: <uuid>    (the end-user the agent is acting on behalf of)
```

`X-contexta-User-Id` is mandatory for any endpoint that touches a user's memories. It's the customer's mapping of their end-user to a stable UUID. contexta does not authenticate this user; the customer does.

## Standard response envelope

All responses are JSON. Success bodies are the resource directly. Error bodies use this shape:

```json
{
  "error": {
    "type": "validation_error",
    "code": "MISSING_FIELD",
    "message": "Field 'session_id' is required.",
    "fields": [{"field": "session_id", "message": "Field 'session_id' is required."}],
    "request_id": "01J9ZXAB1Q2R3S4T5V6W7X8Y9Z"
  }
}
```

Error types:

| Type | HTTP | Notes |
|---|---|---|
| `validation_error` | 422 | Bad payload |
| `authentication_error` | 401 | Missing or invalid bearer |
| `authorization_error` | 403 | Valid bearer, missing scope, or cross-tenant attempt |
| `not_found` | 404 | Resource not found within tenant |
| `quota_exceeded` | 429 | Plan limit hit, hard cap on |
| `rate_limited` | 429 | Per-key RPS hit |
| `conflict` | 409 | Duplicate key, concurrent modification |
| `internal_error` | 500 | Unhandled |
| `service_unavailable` | 503 | DB or Redis unavailable, planned maintenance |

Headers on every response:

```
X-contexta-Request-Id: 01J9ZXAB1Q2R3S4T5V6W7X8Y9Z
X-contexta-Region: eu-fsn1
X-contexta-Quota-Used: 0.42         (only on metered endpoints)
X-contexta-RateLimit-Remaining: 47  (per-key bucket)
X-contexta-RateLimit-Reset: 1716600000
```

Headers on 429:

```
Retry-After: 12
```

## Endpoint catalog

### Observations

#### `POST /v1/observations`

Submit a single observation for asynchronous extraction.

```http
POST /v1/observations
Content-Type: application/json
Authorization: Bearer mk_live_...
X-contexta-User-Id: 11111111-1111-4111-8111-111111111111

{
  "session_id": "33333333-3333-4333-8333-333333333333",
  "messages": [
    {"role": "user", "content": "I prefer Postgres over Mongo"},
    {"role": "assistant", "content": "Noted, I'll prefer Postgres."}
  ],
  "metadata": {"agent": "coding-agent", "version": "1.4.0"},
  "policy": "coding-agent"
}
```

Response 202:

```json
{
  "job_id": "01J9ZXAB1Q2R3S4T5V6W7X8Y9Z",
  "status": "accepted",
  "estimated_processing_seconds": 3
}
```

Constraints:
- Body max 1 MB. Larger returns 422 `PAYLOAD_TOO_LARGE`.
- `messages` must be non-empty array of objects with `role` and `content`.
- `metadata` is opaque, max 4 KB.
- `policy` must be a registered policy name or omitted (uses default).

#### `POST /v1/observations/batch`

Submit up to 50 observations.

```json
{
  "observations": [{...}, {...}]
}
```

Returns `{"jobs": [{"job_id": "...", "status": "accepted"}, ...]}`.

### Retrieval

#### `POST /v1/retrieve`

Hybrid search returning ranked memories.

```http
POST /v1/retrieve
{
  "query_text": "what databases does the user prefer?",
  "session_id": "...",                    (optional)
  "memory_types": ["preference", "fact"], (optional filter)
  "tags": ["database"],                   (optional filter)
  "limit": 20,                            (default 20, max 100)
  "graph_depth": 1,                       (default 1, max 3)
  "include_archived": false,
  "include_cold": false,
  "rerank": false                         (default false; true counts as rerank op)
}
```

Response 200:

```json
{
  "results": [
    {
      "memory_id": "...",
      "memory_type": "preference",
      "title": "Prefers Postgres",
      "content": "User prefers Postgres over Mongo for relational data.",
      "score": 0.872,
      "score_breakdown": {
        "semantic": 0.91,
        "graph": 0.0,
        "importance": 0.75,
        "recency": 0.86,
        "keyword": 0.50
      },
      "tags": ["database"],
      "created_at": "2026-04-12T18:32:11Z"
    }
  ],
  "request_id": "01J...",
  "elapsed_ms": 47
}
```

#### `GET /v1/context`

Token-budgeted context bundle. Used by agents that want a prepackaged blob.

```
GET /v1/context?user_id=...&session_id=...&token_budget=2000&include_user_model=true
```

Response 200:

```json
{
  "user_profile": {...},
  "active_projects": [...],
  "preferences": [...],
  "goals": [...],
  "recent_events": [...],
  "relevant_memories": [...],
  "token_usage": {
    "total": 1853,
    "by_section": {"projects": 642, "goals": 412, "preferences": 213, ...}
  },
  "cache_hit": false,
  "request_id": "01J..."
}
```

### Memories

#### `GET /v1/memories/{id}`

Returns full memory record.

#### `GET /v1/memories/{id}/explain`

Full explainability bundle: extraction source, classification reasoning, scoring breakdown, supersession history.

#### `POST /v1/memories/{id}/pin` etc.

All return `{"memory_id": "...", "is_pinned": true, "audit_event_id": "..."}` shape.

#### `DELETE /v1/memories/{id}`

Hard delete: removes record, embedding, edges, versions, cluster memberships, feedback rows. Returns 204.

#### `GET /v1/memories/timeline/{user_id}`

Chronological event stream of memory creations, updates, supersessions.

### Sessions

#### `POST /v1/sessions`

Start a session. Most customers don't call this — sessions are auto-created on first observation. Useful when you want to register metadata before sending messages.

#### `POST /v1/sessions/{id}/end`

Mark session ended. Triggers Epilogue worker for full-session analysis.

#### `GET /v1/sessions/inspect/{user_id}`

List recent sessions and the memories produced.

### Policies

#### `GET /v1/policies`

List policies registered for this tenant plus built-ins.

#### `POST /v1/policies`

Register a custom policy.

```json
{
  "name": "support-agent",
  "store_rules": [
    {"memory_types": ["preference", "fact", "contact"], "patterns": ["customer.*"]}
  ],
  "ignore_rules": [
    {"patterns": ["^(thanks|hi|hello)$"]}
  ],
  "priority_weights": {"preference": 0.9}
}
```

### Custom schemas

#### `POST /v1/schemas`

Register a custom structured memory schema.

```json
{
  "name": "InvoiceLineItem",
  "field_definitions": [
    {"name": "vendor", "type": "string", "required": true},
    {"name": "amount", "type": "number", "required": true},
    {"name": "currency", "type": "enum", "values": ["USD", "EUR"], "required": true},
    {"name": "due_date", "type": "date", "required": false}
  ]
}
```

### API keys (control plane)

#### `GET /v1/keys`

List keys for the authenticated org.

#### `POST /v1/keys`

Create a key. Returns the token once.

```json
{
  "name": "Production agent",
  "scopes": ["observations:write", "retrieval:read", "memories:read"],
  "project_id": "...",
  "expires_at": "2027-01-01T00:00:00Z"   (optional)
}
```

#### `POST /v1/keys/{id}/rotate`

Rotates: returns new token, old key remains valid for 24 hours.

### Usage and billing

#### `GET /v1/usage`

```json
{
  "period": {"start": "2026-05-01", "end": "2026-06-01"},
  "plan": "solo-pro",
  "limits": {
    "active_memories": 250000,
    "observations": 500000,
    "retrievals": 5000000,
    "reranks": 100000
  },
  "consumed": {
    "active_memories": 91245,
    "observations": 213400,
    "retrievals": 1843200,
    "reranks": 22100
  },
  "overage": {"observations": 0, "retrievals": 0, "reranks": 0},
  "cost_estimate_cents": 6900
}
```

#### `GET /v1/usage/events?start=...&end=...&cursor=...`

Paginated raw events. Last 24h available. Older events available via export.

#### `POST /v1/billing/checkout`

Returns Stripe Checkout URL for plan upgrade.

#### `POST /v1/billing/portal`

Returns Stripe Customer Portal URL for plan management.

### Audit

#### `GET /v1/audit?start=...&end=...&actor_id=...&operation_type=...`

Paginated audit log query. Retention per plan tier.

## Versioning

- The `/v1/` prefix is locked. Breaking changes cut `/v2/`.
- Non-breaking additions (new fields, new endpoints, new optional params) ship within `/v1/`.
- Field deprecations are announced 90 days before removal in next major.
- We maintain `/v1/` for 12 months after `/v2/` is stable.

## Pagination

Cursor-based on all list endpoints:

```
GET /v1/memories?cursor=eyJpZCI6IjAxSjlaIn0&limit=50
```

Response includes `"next_cursor": "..."` or `null`.

## Idempotency

All POST endpoints accept `Idempotency-Key`. The data plane stores keys in Redis with a 24-hour TTL. Replays of an idempotent request return the original response. Keys are scoped per `tenant_id` per `endpoint`.

## Backward compatibility guarantees

- We will never silently change the meaning of a field.
- We will never add a new required field to an existing endpoint.
- We will never remove a field within a major version.
- We may add new error codes within an existing error type.
- We may change the order of `results` arrays if we improve ranking.
