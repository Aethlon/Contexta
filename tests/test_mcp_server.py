"""Test suite for Contexta MCP Server and memory tools."""

import asyncio
import uuid

from dotenv import load_dotenv

from contexta.mcp.server import (
    create_mcp_server,
    create_mcp_server_async,
    create_unified_app,
)
from contexta.mcp.service import ContextaMCPService

# create_mcp_server() reads CONTEXTA_MCP_API_KEY from os.environ, not from the
# settings object. Without this the module only sees the key when some earlier
# test happened to import contexta.benchmarks.benchmark_cortex, which calls
# load_dotenv() as a side effect of its import.
load_dotenv()

ANONYMOUS_ORG = "00000000-0000-0000-0000-0000000000ff"


def test_unified_app_supports_streamable_and_sse_routes(monkeypatch) -> None:
    monkeypatch.delenv("CONTEXTA_MCP_API_KEY", raising=False)
    monkeypatch.setenv("CONTEXTA_MCP_ALLOW_ANONYMOUS", "true")
    server = create_mcp_server(organization_id=ANONYMOUS_ORG)
    app = create_unified_app(server)
    routes = {getattr(route, "path", None) for route in app.routes}

    assert "/mcp" in routes
    assert "/sse" in routes
    assert "/messages" in routes


async def test_sync_bootstrap_runs_inside_a_running_event_loop(monkeypatch) -> None:
    """Regression guard: the blocking factory must not call asyncio.run() reentrantly.

    Bootstrapping the MCP server from an async app (lifespan, parent agent server,
    test) used to raise RuntimeError before a single tool was registered.
    """
    monkeypatch.delenv("CONTEXTA_MCP_API_KEY", raising=False)
    monkeypatch.setenv("CONTEXTA_MCP_ALLOW_ANONYMOUS", "true")

    server = create_mcp_server(organization_id=ANONYMOUS_ORG)
    tools = {tool.name for tool in await server.list_tools()}

    assert "contexta_remember" in tools
    assert server.contexta_service.organization_id == uuid.UUID(ANONYMOUS_ORG)


async def test_mcp():
    print("Testing Contexta MCP Server Tools...")
    server = await create_mcp_server_async()
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]
    print(f"Registered MCP Tools ({len(tool_names)}): {tool_names}")
    assert "contexta_remember" in tool_names
    assert "contexta_recall" in tool_names
    assert "contexta_get_context" in tool_names
    assert "contexta_forget" in tool_names
    assert "contexta_explore_graph" in tool_names
    assert "contexta_dream" in tool_names

    # Test Service directly
    service = ContextaMCPService(organization_id=server.contexta_tenant.organization_id)

    # 1. Remember
    print("\n[1] Testing contexta_remember...")
    rem_res = await service.remember(
        content="Jordan has been learning Rust and built a distributed key-value store called Vortex.",
        user_id="agent_test_user",
        title="Jordan Rust Project",
        tags=["project", "rust"],
        importance=0.8,
    )
    print("Remember result:", rem_res)
    assert rem_res["status"] == "stored"
    mem_id = rem_res["memory_id"]

    # 2. Recall
    print("\n[2] Testing contexta_recall...")
    recall_res = await service.recall(
        query="What project did Jordan build in Rust?",
        user_id="agent_test_user",
        limit=3,
    )
    print(f"Recalled {len(recall_res)} memories:")
    for m in recall_res:
        print(f"  - Score: {m['score']} | Content: {m['content']}")
    assert len(recall_res) > 0
    assert "Vortex" in recall_res[0]["content"] or "Jordan" in recall_res[0]["content"]

    # 3. Context Compilation
    print("\n[3] Testing contexta_get_context...")
    context_str = await service.get_context(user_id="agent_test_user")
    print("Compiled Context:\n" + context_str)
    assert "Jordan" in context_str

    # 4. Explore Graph
    print("\n[4] Testing contexta_explore_graph...")
    graph_res = await service.explore_graph("Jordan", user_id="agent_test_user")
    print("Graph exploration result:", graph_res)

    # 5. Forget
    print("\n[5] Testing contexta_forget...")
    forget_res = await service.forget(mem_id, reason="Testing memory invalidation")
    print("Forget result:", forget_res)
    assert forget_res["status"] == "archived"

    await service.close()
    print("\n>>> ALL MCP TOOLS VERIFIED SUCCESSFULLY! <<<")


if __name__ == "__main__":
    asyncio.run(test_mcp())
