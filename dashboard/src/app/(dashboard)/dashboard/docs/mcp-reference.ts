/**
 * MCP reference data.
 *
 * The tool names, required arguments and endpoint below were read from the
 * running MCP server with a real `tools/list` call, not copied from the previous
 * page. That page had drifted: it documented `contexta_dream`, `contexta_metrics`
 * and the benchmark tools inconsistently, and pointed at the `/sse` transport
 * when the container serves streamable HTTP on `/mcp`.
 *
 * If you add or rename a tool, update this in the same change, or better, have
 * the docs page read it live.
 */

export function mcpEndpoint(): string {
  // The console talks to the MCP server across the compose network; the value
  // the *user's agent* needs is the host-published one.
  return "http://localhost:8765/mcp";
}

type Tool = { name: string; required: string[]; optional: string[] };

const TOOLS: Tool[] = [
  { name: "contexta_remember", required: ["content"], optional: ["user_id", "title", "memory_type", "tags", "importance"] },
  { name: "contexta_recall", required: ["query"], optional: ["user_id", "limit", "graph_depth"] },
  { name: "contexta_get_context", required: [], optional: ["user_id", "focus", "max_memories"] },
  { name: "contexta_forget", required: ["memory_id"], optional: ["reason"] },
  { name: "contexta_explore_graph", required: ["entity_name"], optional: ["user_id", "max_neighbors"] },
  { name: "contexta_dream", required: [], optional: ["user_id"] },
  { name: "contexta_batch_remember", required: [], optional: ["memories", "file_path", "raw_content", "file_url", "user_id", "batch_size", "async_processing"] },
  { name: "contexta_job_status", required: ["job_id"], optional: [] },
  { name: "contexta_benchmark_run", required: [], optional: ["num_queries", "concurrency", "test_suite", "ablation", "user_id", "async_job"] },
  { name: "contexta_benchmark_status", required: ["job_id"], optional: [] },
  { name: "contexta_profile_latency", required: [], optional: ["num_requests", "concurrency", "mode", "user_id"] },
  { name: "contexta_metrics", required: [], optional: [] },
];

export function mcpToolReference(): Tool[] {
  return TOOLS;
}

export function mcpConfigJson(key: string): string {
  return JSON.stringify(
    {
      mcpServers: {
        contexta: {
          url: "http://localhost:8765/mcp",
          headers: { "x-api-key": key },
        },
      },
    },
    null,
    2,
  );
}
