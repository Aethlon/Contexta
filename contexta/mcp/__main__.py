"""CLI entrypoint for Contexta MCP Server.

Usage:
    python -m contexta.mcp                     # Run via stdio (for Cursor, Claude Desktop, Antigravity)
    python -m contexta.mcp --transport sse     # Run via Server-Sent Events (SSE)
"""

from __future__ import annotations

import argparse
import sys

from contexta.mcp.server import create_mcp_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Contexta Agent Memory MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP communication transport (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind for SSE / HTTP transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to bind for SSE / HTTP transport (default: 8765)",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Postgres database URL (defaults to CONTEXTA_DATABASE_URL or localhost:55432)",
    )
    parser.add_argument(
        "--model-server-url",
        default="http://localhost:8001",
        help="Contexta local model server URL for reranking (default: http://localhost:8001)",
    )

    parser.add_argument(
        "--allow-remote",
        action="store_true",
        default=True,
        help="Allow remote connections through tunnels/proxies by disabling DNS rebinding protection (default: True)",
    )

    args = parser.parse_args()
    server = create_mcp_server(
        db_url=args.db_url,
        model_server_url=args.model_server_url,
    )

    if args.transport in ("sse", "streamable-http"):
        from contexta.mcp.server import run_unified_server

        transport_security = None
        if args.allow_remote:
            from mcp.server.transport_security import TransportSecuritySettings

            transport_security = TransportSecuritySettings(
                enable_dns_rebinding_protection=False,
            )

        run_unified_server(
            server,
            host=args.host,
            port=args.port,
            transport_security=transport_security,
        )
    else:
        server.run(transport=args.transport)


if __name__ == "__main__":
    main()
