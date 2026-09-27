# Context Planning, Compression & Assembly

When feeding retrieved memories back to an AI agent, raw context dumps can exhaust token windows and dilute attention. Contexta features an intelligent **Context Planning & Compression Engine** to optimize context payloads.

---

## 1. The Context Assembly Pipeline

```
Retrieved Top-K Memories
           │
           ▼
   [ContextPlanner]      ──► Allocates token budgets across facts, graph, and dialogue turns
           │
           ▼
 [CompressionEngine]    ──► Syntactic reduction & structured JSON deduplication
           │
           ▼
    [ContextBuilder]     ──► Assembles canonical prompt IR with provenance and timestamps
           │
           ▼
    Target AI Agent
```

---

## 2. Dynamic Token Budgeting (`contexta/core/context/planner.py`)

- **Budget Allocation**: Calculates the agent model's maximum context window and dynamically divides capacity:
  - **Core Truths & Rules**: Highest priority tier (never truncated).
  - **Entity Graph Context**: Relational facts and neighboring node summaries.
  - **Episodic Memories**: Graded by reranker score and recency.
- **Graceful Truncation**: Drops lowest-utility episodic memories first when budget boundaries are approached.

---

## 3. Context Compression (`contexta/core/compression/`)

- **Syntactic Redundancy Stripping**: Removes conversational filler, conversational greetings, and discourse boilerplate.
- **Structured Attribute Merging**: Flattens repeated JSON attributes into unified tables or key-value representations.
- **Fact Summarization**: Condenses multi-sentence memories into dense, single-sentence factual assertions without loss of semantic entities.

---

## 4. Context Builder (`contexta/core/context/builder.py`)

Produces the final markdown-formatted block injected into agent system instructions:

```markdown
<contexta_memory_block>
[FACT] TypeScript preferred for backend and frontend services (Confidence: 0.95, Valid From: 2026-01-10)
[PREFERENCE] Always use kebab-case for API route endpoints (Importance: 0.88)
[ENTITY_RELATION] Sarah -> leads -> Platform Team
</contexta_memory_block>
```
Each entry preserves timestamps and entity relations so the reasoning LLM can accurately cite facts and discern sequence.
