# 08 — Web ↔ Backend Integration

This document covers how the Next.js dashboard talks to the backend, how authentication works, and how API keys are created and used by customer agents.

## What's in the repo today vs needed

| Concern | Today | Needed |
|---|---|---|
| Auth | Demo: any email + 8+ char password, base64 cookie | Real: email + password (Argon2id), email verification, magic link, optional Google/GitHub OAuth |
| Session storage | Browser cookie | Server-side sessions via signed JWT or database-backed session |
| API key storage | In-memory dict in `contexta.api.key_store` | Postgres-backed `api_key` table with hashed token |
| Dashboard data | Static mocks in `web/src/lib/data.ts` | Live data from `/v1/...` API |
| Billing UI | None | Stripe Checkout + Customer Portal embedded |
| MFA | None | TOTP via authenticator app (post-launch) |
| Rate limit on auth endpoints | None | Hard limit on sign-in attempts |

## Authentication

### Decisions of record

1. **Primary auth: email + password with Argon2id** (memory-hard, OWASP recommended).
2. **Optional OAuth: Google and GitHub** (most common for AI dev customers).
3. **Email verification mandatory** before first paid action.
4. **Sessions via signed JWT** in HttpOnly cookie. 7-day expiration with sliding window. Stored as `CONTEXTA_session` cookie.
5. **No magic-link auth** at v1 (slower to ship, lower trust signal for B2B).
6. **MFA optional, recommended** for org admins. Post-launch.
7. **NextAuth.js (Auth.js v5)** as the implementation. We do not roll our own.

### Implementation outline

```
web/src/lib/
  auth.ts                # NextAuth config (replaces existing demo auth)
  auth-helpers.ts        # getSession(), requireSession(), signOut()
web/src/app/
  api/auth/[...nextauth]/route.ts  # NextAuth handler

contexta/api/routes/
  auth.py                # POST /v1/auth/signup, /v1/auth/signin, /v1/auth/verify-email, /v1/auth/forgot-password
contexta/services/
  auth.py                # Account model, password hashing, JWT issuing
contexta/models/
  account.py             # User, Organization, OrganizationMember
```

Auth flow:

```
1. User submits email + password to /api/auth/callback/credentials
2. NextAuth calls contexta Python /v1/auth/signin
3. Python verifies password via Argon2id, returns user + org info + a short-lived JWT
4. NextAuth signs its own session JWT, sets HttpOnly cookie
5. Subsequent dashboard requests carry the session cookie
6. Server actions (Next.js) call backend with `Authorization: contexta <session_jwt>` header
```

The `contexta` scheme is internal. The gateway/API tier accepts both `Bearer mk_live_*` (customer agents) and `contexta <session_jwt>` (dashboard). They map to the same actor + tenant context, but session JWTs have full scope and shorter expiration.


### Account / Organization data model

```sql
CREATE TABLE account (
  id              UUID PRIMARY KEY,
  email           CITEXT NOT NULL UNIQUE,
  email_verified  BOOLEAN NOT NULL DEFAULT false,
  password_hash   TEXT,                            -- nullable for OAuth-only accounts
  oauth_provider  VARCHAR(20),                     -- 'google' | 'github' | NULL
  oauth_subject   VARCHAR(80),
  display_name    VARCHAR(120),
  totp_secret     TEXT,                            -- nullable until MFA enrolled
  created_at      TIMESTAMPTZ NOT NULL,
  updated_at      TIMESTAMPTZ NOT NULL,
  last_login_at   TIMESTAMPTZ,
  status          VARCHAR(20) NOT NULL DEFAULT 'active'  -- 'active' | 'suspended' | 'deleted'
);

CREATE TABLE organization (
  id              UUID PRIMARY KEY,
  name            VARCHAR(200) NOT NULL,
  slug            VARCHAR(80) NOT NULL UNIQUE,
  plan_code       VARCHAR(40) NOT NULL DEFAULT 'hobby',
  stripe_customer_id  VARCHAR(80),
  stripe_subscription_id VARCHAR(80),
  status          VARCHAR(20) NOT NULL DEFAULT 'active',
  created_at      TIMESTAMPTZ NOT NULL,
  updated_at      TIMESTAMPTZ NOT NULL
);

CREATE TABLE organization_member (
  organization_id UUID NOT NULL REFERENCES organization(id),
  account_id      UUID NOT NULL REFERENCES account(id),
  role            VARCHAR(20) NOT NULL,            -- 'owner' | 'admin' | 'developer' | 'viewer'
  created_at      TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (organization_id, account_id)
);

CREATE TABLE project (
  id              UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organization(id),
  name            VARCHAR(120) NOT NULL,
  slug            VARCHAR(80) NOT NULL,
  region          VARCHAR(20) NOT NULL DEFAULT 'eu-fsn1',
  hard_cap        BOOLEAN NOT NULL DEFAULT false,
  created_at      TIMESTAMPTZ NOT NULL,
  UNIQUE (organization_id, slug)
);

CREATE TABLE api_key (
  id              UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  project_id      UUID NOT NULL,
  account_id      UUID NOT NULL,                   -- creator
  name            VARCHAR(120) NOT NULL,
  prefix          VARCHAR(20) NOT NULL,
  token_hash      CHAR(64) NOT NULL UNIQUE,        -- sha256 hex
  scopes          TEXT[] NOT NULL,
  status          VARCHAR(20) NOT NULL DEFAULT 'active', -- 'active'|'revoked'|'expired'
  expires_at      TIMESTAMPTZ,
  last_used_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL,
  revoked_at      TIMESTAMPTZ
);

CREATE INDEX ix_api_key_token_hash ON api_key (token_hash);
CREATE INDEX ix_api_key_org_status ON api_key (organization_id, status);
```

This replaces `contexta.api.key_store`'s in-memory dict. The new `ApiKeyRepository` is in `contexta/repositories/api_key_repo.py`.

## Dashboard ↔ backend wiring

### Server actions (Next.js)

All dashboard interactions go through Next.js server actions, which call the Python API server-to-server with the user's session JWT. The browser never sees an API key — keys are only shown once at creation.

```ts
// web/src/app/(dashboard)/api-keys/actions.ts
"use server";
import { contextaFetch } from "@/lib/contexta-api";
import { requireSession } from "@/lib/auth-helpers";

export async function createApiKeyAction(input: {
  name: string;
  projectId: string;
  scopes: string[];
}) {
  const session = await requireSession();
  return contextaFetch("/v1/keys", {
    method: "POST",
    sessionJwt: session.jwt,
    body: JSON.stringify(input),
  });
}
```

`contextaFetch` adds:
- `Authorization: contexta <session_jwt>`.
- `X-contexta-Org-Id: <session.organizationId>` (defense in depth, validated server-side).
- `Content-Type: application/json`.

### What the dashboard fetches at page load

| Page | Endpoints called |
|---|---|
| `/dashboard` | `GET /v1/usage`, `GET /v1/projects`, `GET /v1/audit?limit=10` |
| `/dashboard/projects` | `GET /v1/projects` |
| `/dashboard/projects/[id]` | `GET /v1/projects/{id}`, `GET /v1/usage?project_id={id}` |
| `/dashboard/api-keys` | `GET /v1/keys` |
| `/dashboard/memories` | `POST /v1/retrieve?limit=50` (with default query) |
| `/dashboard/memories/[id]` | `GET /v1/memories/{id}/explain` |
| `/dashboard/usage` | `GET /v1/usage`, `GET /v1/usage?range=30d&aggregate=daily` |
| `/dashboard/billing` | `GET /v1/billing/subscription`, `GET /v1/usage?period=current` |
| `/dashboard/audit` | `GET /v1/audit?range=7d` |
| `/dashboard/settings` | `GET /v1/organization`, `GET /v1/organization/members` |
| `/dashboard/docs` | static |

All page reads are RSC (React Server Components), no client-side fetching at first paint. Mutations go through server actions.

### Caching

Page-level caching uses Next.js `revalidate`:

```ts
// web/src/app/(dashboard)/dashboard/page.tsx
export const revalidate = 30;  // 30s ISR cache for usage cards
```

Mutations call `revalidatePath("/dashboard")` or `revalidateTag("usage")` to invalidate.


## API key flow (the customer's mental model)

Step by step from the customer's perspective:

1. **Sign up** → email + password. Org auto-created, default project named "default".
2. **Verify email** → click link, account active.
3. **Choose plan** → Stripe Checkout (we redirect to Stripe-hosted checkout).
4. **Webhook flips plan** → org now on chosen plan.
5. **Open API Keys tab** → click "Create key".
6. **Modal asks**: name, project, scopes.
7. **Submit** → backend creates row, returns token once. Modal shows the token with a big "Copy" button and a "I've saved this" confirmation.
8. **Customer pastes token** into their `.env`:
   ```env
   CONTEXTA_API_KEY=mk_live_K7x9...
   CONTEXTA_API_URL=https://api.contexta.dev
   ```
9. **Customer's agent code** uses the SDK:
   ```python
   from contexta_client import contexta
   contexta = contexta.from_env()
   contexta.observe(session_id="...", messages=[...])
   context = contexta.context(user_id="...", token_budget=2000)
   ```
10. **Each call** flows: SDK → gateway → data plane → Postgres → response.
11. **Dashboard shows** the calls happening: usage updates within 30 seconds, audit log within seconds.

## Browser ↔ server contract

The browser never holds an API key. Three things only:

1. The session JWT cookie (HttpOnly, signed).
2. CSRF tokens for mutations (NextAuth handles this).
3. UI state (no sensitive data).

When the dashboard needs to display a freshly-created key, the server action returns the token in the response body, the page renders it once with a `useEffect` that clears it from React state on unmount or navigation. We do not store the key in `localStorage` or session storage.

## Cross-tenant guard

Every server action calls `requireSession()` which returns the current `organization_id`. That's the only `organization_id` the action passes to the backend. Even if a malicious dashboard request tampers with the path or body, the gateway re-derives `tenant_id` from the JWT, not from the request body.

The Python control plane double-validates: every route reads `request.state.organization_id` (set by `AuthenticationMiddleware`) and passes it to the repository. The repository's tenant-scoped `WHERE organization_id = $tenant` enforces isolation at the SQL level.

## Production endpoints

The dashboard is deployed at `https://app.contexta.dev` (Vercel or self-hosted Next.js on Hetzner). The backend at `https://api.contexta.dev`. Both behind Cloudflare for CDN + WAF + DDoS protection.

CORS allow-origin is the dashboard's URL only:

```python
# contexta/api/app.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.dashboard_origin],  # https://app.contexta.dev
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["authorization", "content-type", "idempotency-key", "x-contexta-user-id"],
    allow_credentials=True,
)
```

The Go gateway sets the same CORS rules at edge for non-dashboard origins (e.g., when customer agents use SDKs that ride a browser context, rare but possible for browser-based agent tooling).

## Email infrastructure

Transactional emails via Postmark (or Resend as backup). Templates:

| Email | Trigger |
|---|---|
| Welcome | Signup |
| Verify email | Signup + every login until verified |
| Password reset | `/v1/auth/forgot-password` |
| Plan upgrade confirmation | Stripe webhook |
| Plan downgrade scheduled | Stripe webhook |
| Invoice payment succeeded | Stripe webhook |
| Invoice payment failed | Stripe webhook |
| Quota at 80% | Aggregator hook |
| Quota at 100% | Aggregator hook |
| API key created | Audit hook (configurable per org) |
| API key revoked | Audit hook |

All emails carry an `unsubscribe` link only for marketing (none at v1) and a `view in dashboard` link for transactional.

## What customers can self-serve

Without contacting support:
- Signup, email verify, password reset.
- Plan upgrade, downgrade, cancel.
- Project create, rename, delete (cascades to keys).
- Key create, rotate, revoke.
- Hard-cap toggle per project.
- Member invite (Team+), role change.
- Data export (one per quarter included; more is overage).
- Audit log query within retention window.
- Memory list, inspect, delete (with confirmation).
- Policy and schema register / update.

What requires support:
- Region change for an org (data migration involved).
- Custom retention beyond plan defaults.
- SOC 2 / DPA / BAA requests (Enterprise).
- Account deletion for compliance reasons (vs cancel).
- Refunds beyond auto-credit.
