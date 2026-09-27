# Contexta Operator Dashboard

The operator console for a self-hosted Contexta deployment: ingest observations,
inspect what the truth engine kept, and read it back through hybrid retrieval.

```bash
bun install     # or: npm install
bun run dev     # http://localhost:3000
bun run build   # production build
```

## Access control

**The console ships with page authentication OFF.** Contexta is a single-operator,
offline-first tool, so the default is that navigating to `/` renders the console —
no sign-in, no session, no account.

Anyone who can reach port 3000 has the same access as the operator, including
writes. Put it behind a reverse proxy with its own access control, or turn page
auth back on, before exposing it to a network you do not control.

### The switch

| Variable | Default | Effect |
| :--- | :--- | :--- |
| `CONTEXTA_DASHBOARD_AUTH` | `off` | `on` re-enables NextAuth v5 credentials sign-in on every page. Any of `on`/`1`/`true`/`yes`/`required`/`enabled` counts; anything else, or an absent value, means off. |
| `CONTEXTA_DASHBOARD_API_KEY` | *(empty)* | Bootstrap Contexta API key used when auth is off. Recommended. |
| `CONTEXTA_DASHBOARD_ORG_ID` | *(empty)* | Optional organization UUID. |
| `CONTEXTA_DASHBOARD_USER_ID` | *(empty)* | Optional actor UUID. |

To re-enable auth, set `CONTEXTA_DASHBOARD_AUTH=on`, keep `AUTH_SECRET` set, and
restart. You also need an account in the API — create one at `/sign-up`, then
sign in. The signed-in account's organization and user ids become the tenant the
console acts on.

With auth off, `/sign-in` says so plainly instead of rendering a form that does
nothing, and `/api/auth/*` answers `404 authentication_disabled`.

## How the tenant is resolved

Auth off — first match wins:

1. **`contexta_tenant` cookie**, set from the organization panel at the bottom of
   the sidebar. Holds an organization UUID, an actor UUID and/or a bootstrap key.
2. **`CONTEXTA_DASHBOARD_ORG_ID` / `CONTEXTA_DASHBOARD_USER_ID`** from the env.
3. **`CONTEXTA_DASHBOARD_API_KEY`**: the console asks the API which organization
   that key belongs to (`GET /v1/keys`) and displays the answer.

If none of those produce a tenant, the console says **unresolved** and says what
to set. It never falls back to a hidden default organization — the API would
reject the calls anyway, and a silent default is how cross-tenant accidents
happen.

Auth on: the NextAuth session supplies the organization and actor, and the cookie
override is not consulted.

### Known gap: the actor UUID

`GET /v1/entities/graph/{user_id}` is keyed by actor, and no API route returns
the actor behind a bootstrap key (`GET /v1/keys` returns `organization_id` only).
With key-only config the console therefore cannot query the graph, and says so
in the graph panels rather than rendering an empty graph. Set
`CONTEXTA_DASHBOARD_USER_ID` (or fill the user id into the sidebar panel) to
enable it. The same value is what the overview's "Current memories" reads are
scoped by, so setting it makes the whole console operate on one actor.

### What the console sends

`contextaFetch()` in `src/lib/auth-helpers.ts` is the only path to the Python
API, and it attaches:

* `x-api-key` — when a bootstrap key is configured. The key carries the
  organization and actor, so the API resolves the tenant itself.
* `x-organization-id` and `x-user-id` — whenever those ids are known. The API
  cross-checks them against the key and answers `403 organization_mismatch` or
  `403 actor_mismatch` on disagreement, so a wrong tenant fails loudly instead
  of reading another organization's rows.

Identity headers *without* a key are only accepted by the API when it is started
with `CONTEXTA_ALLOW_LEGACY_TENANT_HEADERS=true`; otherwise they get
`401 authentication_required`. That is why `CONTEXTA_DASHBOARD_API_KEY` is the
recommended setting.

## Seeing which organization you are on

* **Header bar** — the org id, truncated, next to an `Auth off` badge.
* **Sidebar, bottom** — the organization panel. Shows the org id, the actor id,
  where the value came from (operator override / environment / discovered from
  API key / signed-in session), a **Verify with API** button that asks the API
  which organization the current identity actually resolves to, and a form to
  change the org id, actor id or bootstrap key, plus a reset back to the env.
* **Settings → Tenant & Access** — the same ids, plus the current auth mode.
* **Overview** — a banner when the tenant is unresolved.

## What the console shows

The overview's **Memory pipeline** strip is the real v1.5 order:

```
ingest -> redact -> extract -> dedup -> score -> graph -> reconcile truth -> embed -> retrieve
```

The memory inspector expands a row to fetch the record's
`structured_data.fact` triple (subject / predicate / object, plus status,
polarity and temporal basis), its `valid_from` / `valid_to` window, and its
supersession lineage from `GET /v1/memories/{id}/explain` (`valid_to` and
`superseded_by_id` per `MemoryVersion`).

`fact_key` is **not** shown: no org-scoped memory route exposes it. It is only
returned by `GET /v1/memory-kernel/facts`, which is additionally scoped to the
authenticated actor being a `memory_user` in the organization, so it is not a
general org-wide read. Adding `fact_key`, `lineage_id` and `superseded_by_id` to
`MemoryDetailResponse` in `contexta/api/routes/memories.py` would close that gap.

## Scripts

| Command | What it does |
| :--- | :--- |
| `bun run dev` | Dev server on :3000 |
| `bun run build` | Production build, then the Tauri static export |
| `bun run start` | Serve the production build |
| `bun run lint` | ESLint (`next lint`) |
| `npx tsc --noEmit` | Typecheck |
