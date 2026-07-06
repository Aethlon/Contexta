# Concepts

contexta is a memory intelligence layer for AI agents. This section covers the core concepts.

## Observations

An observation is a raw conversation turn — the user message and assistant response pair that you submit to contexta. Observations are processed asynchronously: contexta extracts structured memories, classifies them, scores them for importance, and stores them.

→ [Deep dive: Observations](/concepts/observations)

## Memories

A memory is a structured unit of stored intelligence. Each memory has a type (fact, preference, goal, etc.), a title, content, importance score, confidence, entity links, and lifecycle state.

→ [Deep dive: Memories](/concepts/memories)

## Importance Scoring

Each memory is scored for importance (0–1) based on:
- **Emphasis signals** — did the user explicitly emphasize?
- **Decision impact** — does this affect future decisions?
- **Mention frequency** — how often is this referenced?
- **Recency** — when was it last relevant?

Low-importance memories are deprioritized in retrieval and decay faster.

## Decay

Memories that aren't accessed degrade through three states:
- **Active** — full retrieval priority
- **Warm** — lower score penalty
- **Cold** — excluded from default retrieval, available with `include_cold: true`

Pinning a memory protects it from decay.

## Reflection (coming post-PMF)

Autonomous nightly maintenance where contexta reviews stored memories, identifies gaps, consolidates duplicates, and updates the entity graph. No customer action required.

Status: Post-PMF.

## Dream Cycle (coming post-PMF)

Weekly synthetic Q&A evaluation. contexta generates questions about the user based on stored memories, attempts to answer them from memory, and scores retrieval quality. Results feed into the quality dashboard.

Status: Post-PMF.

## Hybrid Retrieval

contexta combines five signals for ranked retrieval: semantic (vector), keyword (full-text), graph (entity relationships), importance, and recency. Results are diversified via MMR and optionally reranked by an LLM.

→ [Deep dive: Retrieval](/concepts/retrieval)
