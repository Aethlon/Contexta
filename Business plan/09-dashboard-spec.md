# 09 — Dashboard Spec

This is the wireframe-level spec for the contexta dashboard at `https://app.contexta.dev`. The current `web/` Next.js app is the foundation; this doc lists every screen and component the production dashboard ships with.

## Top-level navigation

Sidebar (always visible on dashboard pages):

```
[ contexta logo / org switcher ]
─────────────────────────────
  ⌂ Overview
  ▣ Projects
  🔑 API Keys
  📚 Memories
  🛠 Policies & Schemas
  📊 Usage
  💳 Billing
  📜 Audit
  📖 Docs
  ⚙ Settings
─────────────────────────────
  [ User menu ]
```

Org switcher (top of sidebar) lets users with multi-org access switch contexts. For single-org users, it's a static label.

## Screen catalog

### `/sign-in`, `/sign-up`, `/forgot-password`, `/verify-email`

Standard auth flows. Email + password form. OAuth buttons (Google, GitHub). Verification reminder banner if not verified.

### `/dashboard` — Overview

Top row: 4 KPI cards.
- **Active memories** — count, delta vs last 30 days.
- **Observations this period** — count + progress bar to plan limit.
- **Retrieval p95** — milliseconds, sparkline last 7 days.
- **Plan & usage** — plan name, % consumed.

Middle row: two charts side by side.
- **Daily activity** — stacked bar (observations, retrievals, reranks) for 30 days.
- **Top endpoints** — table, top 10 by request count.

Bottom row:
- **Recent audit events** — table, last 10. Click → audit page.
- **Quick links** — "Create key", "Open docs", "View memories".

### `/dashboard/projects` — Project list

Table:

| Project | Region | Memories | Observations (30d) | Retrievals (30d) | Hard cap | Actions |
|---|---|---|---|---|---|---|

Top right: `[ + New project ]`. Modal: name, region (radio), hard cap toggle.


### `/dashboard/projects/[id]` — Project detail

Sticky header: project name, region, plan badge, ID + copy button.

Tabs within page:
- Overview (project-scoped KPIs, mirrors top-level overview).
- Keys (filtered to this project).
- Memories (filtered to this project).
- Sessions.
- Settings (rename, region info, delete).

### `/dashboard/api-keys` — API keys

Top: `[ + Create API key ]`.

Table:

| Name | Prefix | Project | Scopes | Created | Last used | Status | Actions |
|---|---|---|---|---|---|---|---|

Actions: Rotate (modal: warning + confirm), Revoke (confirmation), View audit (filters audit page).

Create modal:
- Name (text input).
- Project (select).
- Scopes (checkboxes with descriptions):
  - `observations:write` — Submit observations
  - `retrieval:read` — Retrieve memories and context
  - `memories:read` — Read memory records
  - `memories:write` — Pin, archive, delete memories
  - `policies:write` — Manage policies
  - `schemas:write` — Manage custom schemas
  - `audit:read` — Read audit log
- Expires at (optional date picker).

After create: full-screen modal with the token in monospace, big "Copy" button, "I've saved this — close" button. The modal blocks dismissal until acknowledged.

### `/dashboard/memories` — Memory inspector

Top: search bar, filter chips.

Filters:
- Type: fact, preference, goal, project, skill, relationship, event, episodic, pattern, contact, custom.
- State: active, warm, cold, archived.
- Pinned only / archived only / superseded only.
- Tags (free-text chips).
- Date range.

Table (paginated, 50/page):

| Title | Type | State | Importance | Confidence | Updated | Tags | Actions |
|---|---|---|---|---|---|---|---|

Row click → side drawer with full memory:
- Full content.
- Structured data (JSON pretty-print).
- Source: session ID + clickable, originating message snippet.
- Scoring breakdown (importance, confidence, freshness, utility, with explanations).
- Entities linked (clickable to entity pages, planned).
- Supersession history (if applicable).
- Actions: pin/unpin, archive/restore, delete (confirm).

### `/dashboard/policies` — Policies & Schemas

Two tabs: Policies, Schemas.

Policies tab:
- Built-in templates (read-only, can clone): coding-agent, crm-agent, tutor-agent.
- Custom policies (table: name, store rules count, ignore rules count, last updated, actions).
- Create / edit form: name, store rules (drag-and-drop list of rule objects), ignore rules, priority weights table.

Schemas tab:
- Custom schemas (table).
- Create / edit form: name, fields (add/remove rows), each field has name + type + required + (for enum) values.

### `/dashboard/usage` — Usage analytics

Hero: large stacked-area chart, 30 days, dimensions: observations, retrievals, reranks. Toggle daily / hourly.

Below:
- Per-key breakdown table.
- Per-endpoint breakdown table.
- Per-project breakdown (if multi-project).
- Cost projection card: "At your current pace, this month's bill will be ~$X".
- Hard cap toggles per project per dimension.
- Export CSV button (last 30 days).

### `/dashboard/billing` — Billing

- Current plan card with name, price, renews-on date, manage in Stripe Portal button.
- Current period usage summary (mirrors usage page hero).
- Payment method (last 4 digits, expiration). Update via Stripe Portal.
- Invoices table, last 12 months, download PDF.
- Plan switcher: see all tiers, click "Upgrade" / "Downgrade" → Stripe Checkout for upgrades, scheduled change for downgrades.
- Managed LLM add-on toggle and bundle picker (Starter / Builder / Pro).

### `/dashboard/audit` — Audit log

Filters: range, actor, operation_type, target_id (paste a memory or session ID).

Table:

| When | Actor | Operation | Target | Details | Request ID |
|---|---|---|---|---|---|

Expandable row with full JSON details. Export CSV.

### `/dashboard/docs` — Embedded docs (links)

Links out to the public docs at `https://docs.contexta.dev` plus copy-pasteable snippets:

- Quick start (env vars).
- Pip SDK install.
- Npm SDK install.
- CLI install.
- OpenAI Assistants integration.
- LlamaIndex integration.
- Anthropic integration.
- LangChain integration.
- Custom agent loop.

These are templated with the user's API key prefix and project ID for instant copy-paste.

### `/dashboard/settings` — Org settings

- General: org name, slug, default region.
- Members: list, invite, role change (owner can demote).
- Roles & permissions: matrix of role × scope (informational).
- MFA enforcement (Team+).
- SSO config (Team+ Google/GitHub, Scale+ SAML).
- Danger zone: delete org (90-day soft delete).

## Components / design system

We need to upgrade the existing custom UI primitives in `web/src/components/ui` to a real component library. Decision:

**Use shadcn/ui (Radix UI under the hood)**. It's the de-facto B2B SaaS component library for Next.js, MIT-licensed, vendored into the codebase (no runtime dependency). Cost: zero. Saves us 4–6 weeks of UI work.

```bash
# After this lands, the web/ folder gets:
pnpm dlx shadcn@latest init
pnpm dlx shadcn@latest add button card dialog dropdown-menu input label select sheet table tabs toast tooltip separator badge avatar skeleton form
```

Hand-rolled primitives in `web/src/components/ui` are replaced.

Charts: **Recharts**. Tables: **TanStack Table**. Date picker: **react-day-picker** (used by shadcn).

Theme: dark mode default (already shipped), light mode toggle (shadcn supports it natively).

## Empty states

Every screen has a tasteful empty state. Examples:

- `/dashboard/api-keys` empty: illustration + "Create your first API key" CTA + link to docs.
- `/dashboard/memories` empty: illustration + "Send your first observation" + curl snippet templated with their key prefix.
- `/dashboard/audit` empty: "No activity yet."

## Loading states

All async sections render shadcn `<Skeleton />` placeholders. No spinners except for inline button states.

## Accessibility

- All interactive elements keyboard-reachable, focus rings visible.
- Color contrast ≥ AA (WCAG 2.2).
- Screen reader labels on all icons.
- Tables have proper `<th scope>` and ARIA labels.
- Form errors announced via `aria-live`.

## Error states

- Network error → toast with retry button.
- 401 → redirect to `/sign-in` with returnTo.
- 403 → "You don't have permission" page with "switch org" hint.
- 429 → toast "Rate limited" with reset countdown.
- 5xx → "Something went wrong" page with request_id and "Contact support" link.

## Performance budget

- LCP < 2 s on a mid-tier laptop on Wi-Fi.
- TTI < 3 s on the same.
- Bundle size: < 250 KB gzipped per route.
- Server actions: p95 < 300 ms for reads, < 600 ms for writes (most of which is Stripe / DB roundtrip).
