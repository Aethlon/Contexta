"""Contexta Model Context Protocol (MCP) Server.

Exposes Contexta 3-Layer persistent memory engine tools to any AI agent
(Cursor, Claude Desktop, Antigravity, AutoGen, CrewAI, LangChain, etc.).
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.mcpserver import MCPServer
from contexta.mcp.service import ContextaMCPService

import mcp.server.mcpserver.utilities.func_metadata as _mcp_func_meta
from pydantic import create_model as _pydantic_create_model

# Compatibility patch for MCP 2.2.0 with Pydantic 2.10+
def _compat_create_wrapped_model(func_name: str, annotation: Any):
    model_name = f"{func_name}Output"
    return _pydantic_create_model(model_name, result=(annotation, ...))

_mcp_func_meta._create_wrapped_model = _compat_create_wrapped_model

logger = logging.getLogger("contexta.mcp")


def create_mcp_server(
    db_url: str | None = None,
    model_server_url: str = "http://localhost:8001",
) -> MCPServer:
    """Create and configure the Contexta MCP Server with all agent memory tools."""
    server = MCPServer("contexta-memory-engine")
    service = ContextaMCPService(db_url=db_url, model_server_url=model_server_url)
    server.contexta_service = service

    @server.tool()
    async def contexta_remember(
        content: str,
        user_id: str = "default_user",
        title: str = "",
        memory_type: str = "episodic",
        tags: list[str] | None = None,
        importance: float = 0.5,
    ) -> dict[str, Any]:
        """Store a durable memory in Contexta with automatic embedding, entity discovery, and deduplication.

        Args:
            content: The text of the memory, fact, user preference, decision, or conversation episode.
            user_id: The user, workspace, or agent scope (e.g. 'alice', 'agent-coder', 'default_user').
            title: Optional short descriptive title for the memory.
            memory_type: One of 'episodic' (events/dialogues), 'semantic' (facts/knowledge), or 'procedural' (skills/instructions).
            tags: Optional category tags (e.g. ['preference', 'tech-stack', 'dietary']).
            importance: Subjective importance rating from 0.0 to 1.0 (default: 0.5).
        """
        return await service.remember(
            content=content,
            user_id=user_id,
            title=title,
            memory_type=memory_type,
            tags=tags,
            importance=importance,
        )

    @server.tool()
    async def contexta_recall(
        query: str,
        user_id: str = "default_user",
        limit: int = 5,
        graph_depth: int = 2,
    ) -> list[dict[str, Any]]:
        """Search and retrieve memories using Contexta's 3-Layer hybrid engine (dense vector + 2-hop entity graph + cross-encoder reranker).

        Args:
            query: The natural language search query or question to recall relevant memories for.
            user_id: The user, workspace, or agent scope to search within.
            limit: Maximum number of relevant memories to return (default: 5).
            graph_depth: Number of knowledge graph relationship hops to expand (default: 2).
        """
        return await service.recall(
            query=query,
            user_id=user_id,
            limit=limit,
            graph_depth=graph_depth,
        )

    @server.tool()
    async def contexta_get_context(
        user_id: str = "default_user",
        focus: str = "",
        max_memories: int = 10,
    ) -> str:
        """Compile an ultra-dense, token-efficient system context snippet for LLM prompts.

        Args:
            user_id: The user or agent scope whose active memory context should be compiled.
            focus: Optional topic or query to tailor the assembled memories around.
            max_memories: Maximum number of memory bullets to include in the context (default: 10).
        """
        return await service.get_context(
            user_id=user_id,
            focus=focus,
            max_memories=max_memories,
        )

    @server.tool()
    async def contexta_forget(
        memory_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Archive or invalidate an obsolete memory or outdated fact by its memory_id.

        Args:
            memory_id: The UUID of the memory record to archive.
            reason: Optional explanation of why the fact was updated or invalidated.
        """
        return await service.forget(
            memory_id=memory_id,
            reason=reason,
        )

    @server.tool()
    async def contexta_explore_graph(
        entity_name: str,
        user_id: str = "default_user",
        max_neighbors: int = 15,
    ) -> dict[str, Any]:
        """Traverse the knowledge graph to discover connected entities, relationship edges, and linked memories.

        Args:
            entity_name: Name of the person, project, place, or concept to explore.
            user_id: The user or agent scope.
            max_neighbors: Maximum number of relationship edges to retrieve (default: 15).
        """
        return await service.explore_graph(
            entity_name=entity_name,
            user_id=user_id,
            max_neighbors=max_neighbors,
        )

    @server.tool()
    async def contexta_dream(
        user_id: str = "default_user",
    ) -> dict[str, Any]:
        """Trigger an offline dream consolidation cycle to evaluate knowledge gaps and synthesize agent insights.

        Args:
            user_id: The user or agent scope to run the consolidation cycle for.
        """
        return await service.dream(user_id=user_id)

    @server.tool()
    async def contexta_batch_remember(
        memories: list[dict[str, Any]] | None = None,
        file_path: str = "",
        raw_content: str = "",
        file_url: str = "",
        user_id: str = "default_user",
        batch_size: int = 50,
        async_processing: bool = True,
    ) -> dict[str, Any]:
        """Ingest large sets of memories (e.g. 1,000 to 10,000+ records) from raw text, files, URLs, or objects.

        Args:
            memories: List of memory objects, each with 'content' and optional 'title', 'tags', 'memory_type', 'importance'.
            raw_content: Raw JSON array, JSONL lines (one JSON per line), or CSV string content (ideal for ChatGPT/Claude in containers).
            file_url: Remote HTTP/HTTPS URL to download dataset from (e.g. raw GitHub or S3 link).
            file_path: Host filesystem path (.json, .jsonl, .csv) when running on same machine.
            user_id: Target user or agent workspace scope.
            batch_size: Chunk size for embedding and database operations (default: 50).
            async_processing: If True, queues the job and processes gradually in the background without blocking the MCP connection.
        """
        return await service.batch_remember(
            memories=memories,
            file_path=file_path,
            raw_content=raw_content,
            file_url=file_url,
            user_id=user_id,
            batch_size=batch_size,
            async_processing=async_processing,
        )

    @server.tool()
    def contexta_job_status(
        job_id: str,
    ) -> dict[str, Any]:
        """Query real-time progress, processed counts, and metrics for a background batch ingestion job.

        Args:
            job_id: The job ID returned by contexta_batch_remember (e.g. 'ingest-a1b2c3d4').
        """
        return service.get_job_status(job_id=job_id)

    @server.tool()
    async def contexta_benchmark_run(
        num_queries: int = 50,
        concurrency: int = 5,
        test_suite: str = "all",
        ablation: bool = True,
        user_id: str = "contexta_benchmark_50k",
        async_job: bool = False,
    ) -> dict[str, Any]:
        """Run statistical evaluation suite over the 50.5K database measuring Recall@1/5/10, MRR, nDCG@10, p50/p95/p99 latency, and graph ablation.

        Args:
            num_queries: Total number of test queries to evaluate (e.g. 20, 50, 100, 500).
            concurrency: Number of parallel concurrent retrieval requests (default: 5).
            test_suite: Category filter ('all', 'contexta_architecture', 'cloud_infra', 'multi_hop_graph', 'temporal_policy').
            ablation: If True, evaluates hybrid 3-layer vs semantic-only (no graph) to measure exact graph contribution and lift.
            user_id: Target user workspace scope to evaluate against.
            async_job: If True (or if num_queries > 60), executes in background and returns job_id for progress polling.
        """
        return await service.run_benchmark(
            num_queries=num_queries,
            concurrency=concurrency,
            test_suite=test_suite,
            ablation=ablation,
            user_id=user_id,
            async_job=async_job,
        )

    @server.tool()
    def contexta_benchmark_status(
        job_id: str,
    ) -> dict[str, Any]:
        """Check the progress, interim metrics, or final report of a running background benchmark job.

        Args:
            job_id: The job ID returned by contexta_benchmark_run (e.g. 'bench-a1b2c3d4').
        """
        return service.get_benchmark_status(job_id=job_id)

    @server.tool()
    async def contexta_profile_latency(
        num_requests: int = 30,
        concurrency: int = 5,
        mode: str = "hybrid",
        user_id: str = "contexta_benchmark_50k",
    ) -> dict[str, Any]:
        """Rapid latency percentile profiling measuring p50, p75, p90, p95, p99, min, max, mean, stddev, and QPS under concurrency.

        Args:
            num_requests: Number of test queries to fire (default: 30).
            concurrency: Number of concurrent parallel workers (default: 5).
            mode: Retrieval pipeline mode ('hybrid' for vector+graph+rerank, or 'semantic_only' for vector+rerank).
            user_id: Workspace user scope.
        """
        return await service.profile_latency(
            num_requests=num_requests,
            concurrency=concurrency,
            mode=mode,
            user_id=user_id,
        )

    @server.tool()
    async def contexta_metrics() -> dict[str, Any]:
        """Retrieve live system metrics, database record counts (memories, entities, graph edges, links), and reranker health."""
        return await service.get_metrics()

    return server


def create_unified_app(
    server: MCPServer,
    transport_security: Any | None = None,
    service: ContextaMCPService | None = None,
) -> Any:
    """Create a unified Starlette ASGI application supporting both Streamable HTTP and SSE.

    Routes:
    - '/' and '/mcp': Streamable HTTP (Claude custom connectors, modern agents)
    - '/sse': POST -> Streamable HTTP, GET -> Server-Sent Events (SSE)
    - '/messages': SSE incoming client message mount
    - '/api/ingest-file' & '/upload': Direct HTTP file upload endpoint for containerized agents
    """
    import json
    from mcp.server.sse import SseServerTransport
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.routing import Mount, Route

    security = transport_security or TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    )

    # 1. Base Streamable HTTP ASGI app
    http_app = server.streamable_http_app(
        streamable_http_path="/",
        transport_security=security,
    )
    streamable_endpoint = http_app.routes[0].endpoint

    # 2. SSE Transport for legacy SSE connections
    sse = SseServerTransport("/messages/", security_settings=security)

    async def handle_sse(scope: Any, receive: Any, send: Any) -> Response:
        async with sse.connect_sse(scope, receive, send) as streams:
            await server._lowlevel_server.run(
                streams[0], streams[1], server._lowlevel_server.create_initialization_options()
            )
        return Response()

    async def sse_endpoint(request: Request) -> Response:
        return await handle_sse(request.scope, request.receive, request._send)

    shared_service = service or getattr(server, "contexta_service", None) or ContextaMCPService()

    async def upload_ingest_endpoint(request: Request) -> Response:
        """HTTP file upload endpoint for ChatGPT/Claude to upload files from cloud containers."""
        try:
            mcp_service = shared_service
            content_type = request.headers.get("content-type", "")
            user_id = request.query_params.get("user_id", "default_user")
            batch_size = int(request.query_params.get("batch_size", 50))

            raw_text = ""
            if "multipart/form-data" in content_type:
                form = await request.form()
                upload_file = form.get("file")
                if upload_file:
                    content_bytes = await upload_file.read()
                    raw_text = content_bytes.decode("utf-8", errors="replace")
                else:
                    return Response(
                        json.dumps({"error": "No 'file' field found in multipart form data."}),
                        status_code=400,
                        media_type="application/json",
                    )
            else:
                body = await request.body()
                raw_text = body.decode("utf-8", errors="replace")

            res = await mcp_service.batch_remember(
                raw_content=raw_text,
                user_id=user_id,
                batch_size=batch_size,
                async_processing=True,
            )
            return Response(json.dumps(res), status_code=200, media_type="application/json")
        except Exception as exc:
            return Response(
                json.dumps({"error": f"Upload ingestion failed: {exc}"}),
                status_code=500,
                media_type="application/json",
            )

    async def benchmark_endpoint(request: Request) -> Response:
        """Run statistical benchmark suite via HTTP."""
        try:
            mcp_service = shared_service
            body = await request.body()
            payload = json.loads(body.decode("utf-8")) if body else {}
            num_queries = int(payload.get("num_queries", request.query_params.get("num_queries", 50)))
            concurrency = int(payload.get("concurrency", request.query_params.get("concurrency", 5)))
            test_suite = str(payload.get("test_suite", request.query_params.get("test_suite", "all")))
            ablation = bool(payload.get("ablation", True))
            async_job = bool(payload.get("async_job", False))
            user_id = str(payload.get("user_id", "contexta_benchmark_50k"))

            result = await mcp_service.run_benchmark(
                num_queries=num_queries,
                concurrency=concurrency,
                test_suite=test_suite,
                ablation=ablation,
                user_id=user_id,
                async_job=async_job,
            )
            return Response(json.dumps(result), status_code=200, media_type="application/json")
        except Exception as exc:
            return Response(json.dumps({"error": str(exc)}), status_code=500, media_type="application/json")

    async def benchmark_status_endpoint(request: Request) -> Response:
        """Query background benchmark status."""
        mcp_service = shared_service
        job_id = request.path_params.get("job_id", "")
        status_info = mcp_service.get_benchmark_status(job_id)
        return Response(json.dumps(status_info), status_code=200, media_type="application/json")

    async def profile_endpoint(request: Request) -> Response:
        """Measure latency percentiles under load."""
        try:
            mcp_service = shared_service
            body = await request.body()
            payload = json.loads(body.decode("utf-8")) if body else {}
            num_requests = int(payload.get("num_requests", request.query_params.get("num_requests", 30)))
            concurrency = int(payload.get("concurrency", request.query_params.get("concurrency", 5)))
            mode = str(payload.get("mode", request.query_params.get("mode", "hybrid")))
            user_id = str(payload.get("user_id", "contexta_benchmark_50k"))

            result = await mcp_service.profile_latency(
                num_requests=num_requests,
                concurrency=concurrency,
                mode=mode,
                user_id=user_id,
            )
            return Response(json.dumps(result), status_code=200, media_type="application/json")
        except Exception as exc:
            return Response(json.dumps({"error": str(exc)}), status_code=500, media_type="application/json")

    async def metrics_endpoint(request: Request) -> Response:
        """Retrieve live metrics & database statistics."""
        try:
            mcp_service = shared_service
            metrics = await mcp_service.get_metrics()
            return Response(json.dumps(metrics), status_code=200, media_type="application/json")
        except Exception as exc:
            return Response(json.dumps({"error": str(exc)}), status_code=500, media_type="application/json")

    # 3. Unified routing table
    http_app.routes.append(Route("/mcp", endpoint=streamable_endpoint))
    http_app.routes.append(Route("/sse", endpoint=streamable_endpoint, methods=["POST"]))
    http_app.routes.append(Route("/sse", endpoint=sse_endpoint, methods=["GET"]))
    http_app.routes.append(Mount("/messages", app=sse.handle_post_message))
    http_app.routes.append(Route("/api/ingest-file", endpoint=upload_ingest_endpoint, methods=["POST"]))
    http_app.routes.append(Route("/upload", endpoint=upload_ingest_endpoint, methods=["POST"]))
    http_app.routes.append(Route("/api/benchmark", endpoint=benchmark_endpoint, methods=["POST", "GET"]))
    http_app.routes.append(Route("/api/benchmark-status/{job_id}", endpoint=benchmark_status_endpoint, methods=["GET"]))
    http_app.routes.append(Route("/api/profile", endpoint=profile_endpoint, methods=["POST", "GET"]))
    http_app.routes.append(Route("/api/metrics", endpoint=metrics_endpoint, methods=["GET"]))

    return http_app


def run_unified_server(
    server: MCPServer,
    host: str = "127.0.0.1",
    port: int = 8765,
    transport_security: Any | None = None,
) -> None:
    """Run the unified Streamable HTTP + SSE MCP server with uvicorn."""
    import uvicorn

    app = create_unified_app(server, transport_security=transport_security)
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=server.settings.log_level.lower(),
    )
    uv_server = uvicorn.Server(config)
    uv_server.run()
