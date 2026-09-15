<p align="center">
  <img src="assets/logo.png" alt="Contexta Logo" width="620"/>
</p>

<h3 align="center">The Open-Source, Long-Term Memory Intelligence Engine for AI Agents</h3>

<p align="center">
  <strong>Give your LLMs and autonomous agents persistent, human-like memory across sessions.</strong><br/>
  100% self-hosted • Sovereign & offline-first • Zero third-party SaaS fees • Strict data privacy
</p>

<p align="center">
  <a href="#-the-problem-why-ai-agents-need-memory">Why Contexta</a> •
  <a href="#-how-contexta-works">How It Works</a> •
  <a href="#-key-superpowers">Superpowers</a> •
  <a href="#-sdk-integration-local-preview">SDKs</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="docs/">Documentation</a>
</p>

---

## 💡 What is Contexta?

**Contexta is a self-hosted memory layer designed specifically for AI agents, chatbots, and autonomous workflows.**

Just like humans remember past conversations, preferences, and important life details, Contexta equips your AI agents with a continuous, long-term memory engine. Instead of treating every conversation as a blank slate, your agents remember who they are talking to, what happened weeks ago, and how facts evolve over time.

Contexta runs entirely on your own infrastructure (Docker, local models, or your cloud of choice). Your sensitive user data never leaves your environment, and you avoid expensive third-party memory API subscriptions.

---

## 🧩 The Problem: Why AI Agents Need Memory

Every modern AI agent faces two critical bottlenecks:

1. **Amnesia & Context Bloat**: When a chat finishes, the agent forgets everything. If you try to fix this by cramming entire conversation histories into the LLM prompt, you burn thousands of dollars in token costs, hit context window limits, and cause the model to suffer from "lost in the middle" hallucinations.
2. **Privacy Risks & SaaS Lock-in**: Offloading user memory to proprietary, closed-source cloud memory services exposes sensitive user chats, creates vendor lock-in, and introduces recurring per-call pricing.

**Contexta solves both.** It runs directly alongside your application, intelligently filtering and storing only what matters, keeping facts updated, and serving precise, high-salience context in milliseconds.

---

## ⚙️ How Contexta Works

Contexta operates like a cognitive cycle running silently in the background:

```
┌─────────────────┐       ┌─────────────────────────┐       ┌──────────────────────┐
│  1. OBSERVE     │ ────> │  2. DREAM & CONSOLIDATE │ ────> │  3. RECALL           │
│  Conversation   │       │  Extract facts, link    │       │  Precise, budgeted   │
│  is ingested    │       │  entities & update truth│       │  context in <10ms    │
└─────────────────┘       └─────────────────────────┘       └──────────────────────┘
```

1. **Observe (Ingest)**:
   As your user interacts with your agent, you pass the messages to Contexta via a single SDK call. Contexta automatically sanitizes the text, redacting API keys, passwords, and secrets before anything is saved.

2. **Dream (Consolidate & Truth Maintenance)**:
   In the background, autonomous workers run "dream cycles":
   - **Fact Extraction**: Automatically identifies user preferences, facts, and relationships.
   - **Knowledge Graph Linking**: Connects people, projects, places, and concepts.
   - **Contradiction Resolution**: If a user says *"I moved from New York to London"*, Contexta invalidates the outdated location and updates the active fact so the agent never gets confused.

3. **Recall (Context Injection)**:
   When your agent needs to generate a response, Contexta fuses dense vector similarity (`pgvector`), lexical keyword matching, and knowledge graph traversal. It outputs a neat, token-budgeted memory briefing ready to drop right into your system prompt.

---

## ✨ Key Superpowers

- 🛡️ **100% Sovereign & Offline-Ready**:
  Comes out-of-the-box with local Qwen3 models (`Qwen/Qwen3-Embedding-0.6B` and `Qwen/Qwen3-Reranker-0.6B`). Runs completely offline without external cloud keys or internet access. Online cloud models (OpenAI, DeepSeek, Anthropic) are fully supported whenever you want them.

- ⚡ **Ultra-Low Latency (<10ms Data-Plane)**:
  Engineered with high-throughput Go microservices for real-time reads and writes, paired with PostgreSQL + pgvector for rock-solid persistence.

- 🧠 **Living Truth Maintenance**:
  Memories aren't static vectors. Contexta actively tracks memory lineage, supersedes contradicting facts, and decays stale information over time.

- 🏢 **Multi-Tenant by Design**:
  Isolated memory partitions by organization, user, and session. Complete cryptographic and relational segregation prevents data leaks between users.

- 🖥️ **Interactive Visual Console**:
  Includes a sleek management dashboard to inspect memories, search entities, visualize relationships in an interactive graph, and test recall queries live.

- 🔌 **Native MCP Server Support**:
  Plug Contexta directly into **Cursor, Windsurf, and Claude Desktop** via the Model Context Protocol (MCP) to give your favorite AI coding editors persistent memory of your projects.

---

## 📦 SDK Integration

> [!IMPORTANT]
> **Status: Local Monorepo Preview (Public Registry Release Coming Soon)**  
> The official Python and TypeScript client SDKs are currently available locally inside this repository under [`clients/python`](clients/python) and [`clients/typescript`](clients/typescript).  
> They will be published to PyPI (`contexta-client`) and npm (`@contexta/client`) in the upcoming public release. In the meantime, you can install or link them directly from this repository.

### Python SDK (Local Development)

Install locally in editable mode:
```bash
pip install -e clients/python
```

```python
from contexta_client import contexta

# Automatically connects to CONTEXTA_API_URL and CONTEXTA_API_KEY
memory = contexta.from_env()

# 1. Observe a conversation
memory.observe(
    user_id="user_123",
    messages=[
        {"role": "user", "content": "I prefer historic boutique hotels and love drinking matcha tea."},
        {"role": "assistant", "content": "Got it! I will remember that for your future itineraries."}
    ],
)

# 2. Retrieve relevant context for your next prompt
ctx = memory.context(user_id="user_123", token_budget=1500)

# 3. Inject into your system prompt
system_prompt = f"You are a helpful travel assistant.\n\n{ctx.to_system_prompt()}"
```

### TypeScript SDK (Local Development)

Install or link locally:
```bash
npm install ./clients/typescript
```

```typescript
import { contexta } from "@contexta/client";

const memory = contexta.fromEnv();

// 1. Observe an interaction
await memory.observe({
  userId: "user_123",
  messages: [
    { role: "user", content: "I prefer historic boutique hotels and love drinking matcha tea." }
  ]
});

// 2. Retrieve structured memory context
const ctx = await memory.context({ userId: "user_123" });
console.log(ctx.toSystemPrompt());
```

---

## ⚡ Quick Start

Get the entire Contexta stack running locally in under two minutes:

### 1. Launch the Stack

**macOS & Linux:**
```bash
./entrypoint.sh
```

**Windows (PowerShell):**
```powershell
.\start.ps1
```

*(Or use Docker directly: `cp .env.example .env && docker compose up -d`)*

> **Offline by default**: On first launch, the local embedding & reranker models download automatically to `./models`. Zero cloud API keys required.

### 2. Open the Dashboard

Open your browser to **[http://localhost:3000](http://localhost:3000)**:
- Log in with any email and password (minimum 8 characters in development mode).
- Head to **API Keys** to generate an API key for your applications.
- Explore the **Memory Inspector** and **Entity Graph** as you ingest data!

---

## 📚 Where to Go Next

To keep this README focused on what Contexta is as a software product, in-depth technical guides, API specs, and architectural deep dives are organized in dedicated resources:

| Resource | Description |
| :--- | :--- |
| 📖 **[Developer Documentation (`docs/`)](docs/)** | Full Nextra documentation portal containing step-by-step quickstarts, integration guides (LangChain, LlamaIndex, OpenAI Assistants, Claude), concept deep-dives (truth maintenance, hybrid retrieval, decay math), and complete API references. |
| 🤖 **[Contributor Playbook (`AGENTS.md`)](AGENTS.md)** | Architectural invariants, service boundary definitions, testing suites, multi-tenant rules, and coding standards for developers and autonomous agents. |
| 🔌 **[Model Context Protocol (`contexta/mcp/`)](contexta/mcp/)** | Instructions for setting up Contexta as an MCP server with Cursor, Windsurf, or Claude Desktop. |
| 🤝 **[Contributing Guidelines (`CONTRIBUTING.md`)](CONTRIBUTING.md)** | Information on community contributions, bug reports, and dashboard feature requests. |

---

## 📜 License

Contexta is open-source software licensed under the **Apache 2.0 License**. You are free to use, modify, and distribute it for both personal and commercial projects.
