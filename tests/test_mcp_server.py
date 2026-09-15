"""Test suite for Contexta MCP Server and memory tools."""

import asyncio
from contexta.mcp.server import create_mcp_server
from contexta.mcp.service import ContextaMCPService


async def test_mcp():
    print("Testing Contexta MCP Server Tools...")
    server = create_mcp_server()
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
    service = ContextaMCPService()

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
