"""Contexta Model Context Protocol (MCP) Server.

Enables AI agents (Cursor, Claude Desktop, Antigravity, AutoGen, CrewAI, etc.)
to natively remember, recall, synthesize context, and traverse persistent
knowledge graphs via Contexta's 3-Layer memory engine.
"""

from contexta.mcp.server import create_mcp_server

__all__ = ["create_mcp_server"]
