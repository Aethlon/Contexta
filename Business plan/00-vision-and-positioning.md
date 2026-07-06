# 00 — Vision and Positioning

## What contexta is

contexta is a hosted memory layer that AI agents call instead of stuffing their context window or rolling their own vector DB. Two methods make the product real:

```
contexta.observe(...)   # remember
contexta.context(...)   # recall
```

Customers send observations (conversation turns, tool outputs, session metadata), and contexta returns ranked, structured context on demand. The SDK is the product surface; the HTTP API is the wire format underneath.

It is not a vector database, not a chat session store, not a "save messages to S3" wrapper. The core differentiator is the engine that sits between raw observations and retrieval: extraction, classification, importance scoring, truth maintenance (contradictions resolved automatically), entity resolution, clustering, hybrid retrieval, decay, and explainability. Autonomous maintenance (reflection, dream cycle) ships post-PMF.

## Who we sell to

In priority order:

1. **Indie devs and small teams building AI agents** — vertical agents (coding, CRM, tutoring, customer support, scheduling), agent frameworks, agent companies pre-Series A. This is the wedge: $19–$249/mo, self-serve signup, value visible in 5 minutes.
2. **Mid-market AI product teams** — companies shipping AI features inside larger SaaS products. Want predictable pricing, audit logs, SOC 2 readiness, EU data residency. $999–$9,999/mo, light-touch sales.
3. **Enterprise** — banks, healthcare, defense contractors. Want VPC peering, dedicated infrastructure, SSO, BAA, SOC 2 Type II. $25k+/mo annual contracts. Not a Year 1 priority.

We do not sell to consumers, end users, or "AI assistant for personal use" customers. The contract is always B2D (business to developer) or B2B.

## What customers get

- A REST API with hashed bearer tokens, scoped per project.
- Pip and npm SDKs.
- A CLI for setup, smoke tests, policy registration.
- A dashboard for projects, API keys, memory inspection, usage, billing, audit logs.
- Memory explainability (`explain()` returns extraction source, scoring breakdown, supersession history).
- Integrations: OpenAI Assistants, LlamaIndex, Anthropic, LangChain, plus a generic protocol for custom agent loops.
- 99.9% uptime SLA on Team and above.

## What customers do not get

- The source code of the engine.
- The ability to self-host the production stack. (We may ship a "dev container" for offline testing; that container is not licensed for production.)
- Open-sourced extraction prompts, scoring weights, or reflection logic.

## The wedge

Most agent developers reach for one of three options today:

1. **Stuff context windows manually.** Works at small scale, breaks at growth. Token costs explode.
2. **Roll their own pgvector setup.** Months of engineering for what looks like "just store and retrieve embeddings." Then they hit retrieval quality issues, contradiction handling, decay, multi-tenancy.
3. **Use Mem0/Letta/Zep.** These products solve the storage layer but most stop at "embedding + simple importance score." None ship a production-grade reflection engine, dream cycle, or compression engine.

contexta's wedge is **explainable, self-improving memory** with zero engineering cost to integrate. Five minutes to first observation, fifteen minutes to integrated agent.

The marketing line is: *"`contexta.observe()` to remember. `contexta.context()` to recall. The rest is implementation."*

Secondary line: *"Memory that understands. Not a vector database."*

## Differentiators (v1)

1. **SDK-first.** Two-line integration. `observe()` to remember, `context()` to recall. Everything else is leverage on top.
2. **Importance framework with type-based base scores plus learned modifiers.** Repetition, recency, emphasis, decision impact, measured utility from the feedback engine.
3. **Truth maintenance.** Contradictions are detected and resolved automatically. Old facts are versioned, not deleted.
4. **Cluster-aware hybrid retrieval.** Cluster-first semantic search + keyword + graph expansion + importance/recency weighting in a single SQL pass. Sub-100ms p99 at 1M memories per tenant.
5. **Tenant isolation enforced at three layers.** Repository tenant scope, Postgres row-level security, and CI cross-tenant tests. No "I forgot to add the WHERE clause" data leaks.
6. **Token-aware context planner.** Customers specify a token budget; contexta allocates across projects/goals/preferences/events using configurable weights.
7. **Sensitive data filtering at ingestion.** Passwords, API keys, JWTs, payment cards, OTPs are redacted before extraction. No way for a secret to enter the memory store.
8. **Memory explainability.** Every memory has a full lineage: which observation produced it, why it was classified that way, the scoring breakdown, supersession history.

## What ships post-PMF (deferred)

These are designed and partially implemented but not part of the public v1 product:

- **Reflection engine** — nightly autonomous maintenance.
- **Dream cycle** — weekly self-evaluation and gap identification.
- **Memory compression engine** — deep summarization beyond per-entity.
- **Cross-cluster retrieval optimization** — hierarchical clustering.
- **Multimodal observations** — images, audio, video.

The reasoning: closed beta needs to prove that customers integrate fast, retrieval is useful, memory stays correct, and they keep using it. Reflection and dream are valuable for retention at scale but don't drive PMF.

## What "active developer relationship" means

This is a competitive moat for indie/SMB customers who feel ignored by larger infra companies.

Rules of engagement:

- Every paying customer gets a Slack Connect (or Discord) channel with at least one engineer in it.
- Tier 1 (Hobby): community Discord with weekly office hours.
- Tier 2 (Solo Pro / Team): dedicated channel, response within 24h business hours.
- Tier 3 (Scale): dedicated channel, response within 4h business hours, named SRE point of contact.
- Customer-requested patches that are not infrastructure-blocked ship within one week. We publish a "shipped this week from customer feedback" note in changelog.
- Pricing changes are communicated 30 days in advance, never silently.

## What we will not do

- Run an open core or community edition.
- Take money for "lifetime deals" (AppSumo, etc).
- Ship a free tier before we have unit economics nailed.
- Sell tokens. We are not an LLM aggregator. BYOK is the model.
- Add features to chase competitor parity. We add features that map to a customer's stated workflow.
- Ship reflection / dream cycle / autonomous self-optimization in the public v1 wedge. Those are the right features for retention at scale, but not for proving PMF.
- Pretend to support real-time bidirectional streaming, GraphQL, or multimodal observations at v1. Text REST only.
