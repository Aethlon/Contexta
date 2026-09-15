# Contexta Model Context Protocol (MCP) Server

A high-performance Model Context Protocol (MCP) server that empowers any AI agent (Claude Desktop, Cursor, Antigravity, AutoGen, CrewAI, LangChain, etc.) with **Contexta's 3-Layer Persistent Memory Architecture**:
1. **Layer 1: Relational Facts** - ACID tenant isolation, structured metadata, timestamps, and validity ranges in PostgreSQL.
2. **Layer 2: Dense Semantic Vectors** - Fast pgvector indexing with local embeddings for high-throughput candidate retrieval.
3. **Layer 3: 2-Hop Spreading Activation Graph** - Dynamic entity co-occurrence edges and neural cross-encoder reranking.

---

## 🚀 Quickstart

### 1. Ensure Services are Running
Contexta requires Postgres with `pgvector` (port 55432 or 5432) and the local model server (port 8001):
```bash
docker compose up -d
```

### 2. Run via Stdio (Default)
```bash
python -m contexta.mcp
```

### 3. Run via Server-Sent Events (SSE)
```bash
python -m contexta.mcp --transport sse --port 8765
```

---

## 🛠️ Tools Exposed to AI Agents

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `contexta_remember` | `content`, `user_id`, `title`, `memory_type`, `tags`, `importance` | Stores a durable memory with auto-vector embedding, entity resolution, and typed semantic relations (`integrates_with`, `is_a`, etc.). |
| `contexta_batch_remember` | `memories`, `raw_content`, `file_url`, `file_path`, `user_id`, `batch_size`, `async_processing` | Ingests large datasets (up to 10k+ records) from objects, raw JSONL/JSON/CSV text, files, or URLs with background chunking. |
| `contexta_job_status` | `job_id` | Queries real-time progress, processed record counts, and elapsed metrics for a background ingestion job. |
| `contexta_recall` | `query`, `user_id`, `limit`, `graph_depth` | Executes 3-layer hybrid retrieval (vector similarity + 2-hop graph traversal + neural cross-encoder reranking). |
| `contexta_get_context` | `user_id`, `focus`, `max_memories` | Formats an ultra-dense, token-efficient system context snippet for LLM prompts. |
| `contexta_forget` | `memory_id`, `reason` | Archives or invalidates outdated facts (e.g. user moved or updated preferences). |
| `contexta_explore_graph` | `entity_name`, `user_id`, `max_neighbors` | Traverses the knowledge graph to discover related entities, typed edge relationships, and linked memories. |
| `contexta_dream` | `user_id` | Triggers a dream consolidation cycle to detect knowledge gaps and synthesize agent insights. |

---

## 📥 Ingesting Files from Cloud Agents (ChatGPT, Claude)

When AI agents run inside cloud sandboxes (e.g. ChatGPT Advanced Data Analysis or Claude Web), their local filesystem (`/mnt/data/...`) is isolated and not accessible to the Contexta server. We support two direct ingestion methods:

### Method 1: Pass `raw_content` via the MCP Tool
ChatGPT can read its local generated file and pass the string directly:
```python
contexta_batch_remember(
    raw_content=open("/mnt/data/contexta_benchmark/contexta_10k.jsonl").read(),
    batch_size=50
)
```

### Method 2: HTTP File Upload Endpoint
ChatGPT can post the file directly to the live Contexta upload endpoint from its Python interpreter:
```python
import requests

with open("/mnt/data/contexta_benchmark/contexta_10k.jsonl", "rb") as f:
    resp = requests.post(
        "https://apically-literary-tajuana.ngrok-free.dev/api/ingest-file",
        files={"file": f},
        params={"batch_size": 50}
    )
print(resp.json())  # Returns: {"job_id": "ingest-...", "status": "queued", "total_records": 10000}
```

---

## 🔌 Agent Configurations

### Claude Desktop
Add to `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):
```json
{
  "mcpServers": {
    "contexta": {
      "command": "C:/Users/username/Desktop/Memento/.venv/Scripts/python.exe",
      "args": ["-m", "contexta.mcp"],
      "env": {
        "CONTEXTA_DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:55432/contexta"
      }
    }
  }
}
```

### Cursor IDE
Add to `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "contexta": {
      "command": "python",
      "args": ["-m", "contexta.mcp"],
      "env": {
        "CONTEXTA_DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:55432/contexta"
      }
    }
  }
}
```

### Antigravity IDE / Gemini CLI
Add to `~/.gemini/antigravity-ide/mcp/contexta/mcp_config.json`:
```json
{
  "command": "python",
  "args": ["-m", "contexta.mcp"],
  "env": {
    "CONTEXTA_DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:55432/contexta"
  }
}
```

---

## 🐍 Python Agent Example (LangChain / Custom Agent)

```python
import asyncio
from contexta.mcp.service import ContextaMCPService

async def main():
    service = ContextaMCPService()
    
    # 1. Store memory
    res = await service.remember(
        "Alex prefers TypeScript and Tailwind for all frontend work, and deploys to Vercel.",
        user_id="developer_alex",
        tags=["preference", "tech-stack"]
    )
    print("Stored memory:", res["memory_id"])
    
    # 2. Recall memory with 3-Layer hybrid search
    memories = await service.recall(
        "What tech stack does Alex use for frontend?",
        user_id="developer_alex"
    )
    for m in memories:
        print(f"[{m['score']:.3f}] {m['content']}")

asyncio.run(main())
```
