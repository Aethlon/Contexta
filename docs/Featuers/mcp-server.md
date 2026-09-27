# Model Context Protocol (MCP) Server

Contexta provides a native, high-throughput **Model Context Protocol (MCP)** server that seamlessly connects Claude Desktop, Cursor, Antigravity, AutoGen, CrewAI, and LangChain to Contexta’s 3-layer persistent memory engine.

---

## 1. Supported Transports

The server can run via standard I/O (default for desktop clients) or Server-Sent Events (SSE) for distributed setups:

```bash
# Stdio Mode (Claude Desktop / Cursor)
python -m contexta.mcp

# SSE Mode (Networked Agents)
python -m contexta.mcp --transport sse --port 8765
```

---

## 2. Exposed Agent Tools

| Tool | Core Parameters | Functionality |
| :--- | :--- | :--- |
| `contexta_remember` | `content`, `title`, `memory_type`, `tags`, `importance` | Stores a durable memory with auto-vector embedding and bulk entity resolution. |
| `contexta_batch_remember` | `memories`, `raw_content`, `file_path`, `batch_size` | Ingests up to 10k+ records from JSONL/JSON/CSV with async background worker jobs. |
| `contexta_job_status` | `job_id` | Monitors batch ingestion progress, processed item counts, and elapsed metrics. |
| `contexta_recall` | `query`, `limit`, `graph_depth` | Executes 3-layer hybrid recall (dense vector + lexical + graph traversal + reranker). |
| `contexta_get_context` | `user_id`, `focus`, `max_memories` | Formats an ultra-dense, token-budgeted prompt snippet ready for injection. |
| `contexta_forget` | `memory_id`, `reason` | Archives or marks an outdated fact invalid (`valid_to = now()`). |
| `contexta_explore_graph` | `entity_name`, `max_neighbors` | Traverses entity nodes, typed edge relationships, and connected memories. |
| `contexta_dream` | `user_id` | Triggers on-demand memory consolidation and graph summarization. |

---

## 3. Connecting to AI Assistants

### Claude Desktop
Add to your `claude_desktop_config.json`:
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

### Cursor IDE
Add to `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "contexta": {
      "command": "python",
      "args": ["-m", "contexta.mcp"]
    }
  }
}
```
