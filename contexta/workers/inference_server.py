"""Local generative inference server for Contexta extraction workloads."""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from contexta.contracts.extraction import (
    SYSTEM_PROMPT as EXTRACTION_SYSTEM_PROMPT,
)
from contexta.contracts.extraction import (
    ExtractedClaim as ExtractionClaim,
)
from contexta.contracts.extraction import (
    ExtractionEnvelope,
    memory_schema,
)
from contexta.core.extraction.chunking import (
    DEFAULT_CHUNK_SENTENCES,
    DEFAULT_MAX_CHUNK_CHARS,
    merge_claims,
    salvage_json_array,
    split_conversation,
)

logger = logging.getLogger("contexta.inference")

OLLAMA_URL = os.environ.get("CONTEXTA_INFERENCE_OLLAMA_URL", "http://localhost:11434").rstrip("/")
INFERENCE_MODEL = os.environ.get(
    "CONTEXTA_INFERENCE_MODEL",
    "contexta-lfm-extract",
)
NUM_CTX = int(os.environ.get("CONTEXTA_INFERENCE_NUM_CTX", "16384"))
NUM_PREDICT = int(os.environ.get("CONTEXTA_INFERENCE_NUM_PREDICT", "4096"))
# A chunk holds at most DEFAULT_CHUNK_SENTENCES facts, so it needs far fewer
# output tokens than a whole conversation would.
CHUNK_MAX_TOKENS = int(os.environ.get("CONTEXTA_INFERENCE_CHUNK_MAX_TOKENS", "2048"))
CHUNK_SENTENCES = int(
    os.environ.get("CONTEXTA_INFERENCE_CHUNK_SENTENCES", str(DEFAULT_CHUNK_SENTENCES))
)
CHUNK_MAX_CHARS = int(
    os.environ.get("CONTEXTA_INFERENCE_CHUNK_MAX_CHARS", str(DEFAULT_MAX_CHUNK_CHARS))
)
HTTP_TIMEOUT_SECONDS = float(os.environ.get("CONTEXTA_INFERENCE_TIMEOUT_SECONDS", "900"))


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[Message]
    temperature: float = 0.0
    max_tokens: int = NUM_PREDICT
    num_ctx: int = NUM_CTX


class ChatResponse(BaseModel):
    id: str
    model: str
    content: str
    finish_reason: str | None
    metrics: dict[str, Any]


class ExtractRequest(BaseModel):
    conversation: str = Field(min_length=1)
    model: str | None = None
    num_ctx: int = NUM_CTX
    max_tokens: int = NUM_PREDICT
    # Chunking controls. Defaults are the measured values; see
    # contexta.core.extraction.chunking.
    chunk_sentences: int = CHUNK_SENTENCES
    chunk_max_chars: int = CHUNK_MAX_CHARS


class ExtractResponse(BaseModel):
    """Extraction result.

    `claims` is the response field name callers already use; it is populated from
    the canonical envelope's `memories` array so the wire shape stays stable while
    the model emits the contract it was fine-tuned on.
    """

    model: str
    claims: list[dict[str, Any]]
    raw_content: str
    metrics: dict[str, Any]


def _timings(payload: dict[str, Any], wall_ms: float) -> dict[str, Any]:
    prompt_count = int(payload.get("prompt_eval_count") or 0)
    prompt_ns = int(payload.get("prompt_eval_duration") or 0)
    output_count = int(payload.get("eval_count") or 0)
    output_ns = int(payload.get("eval_duration") or 0)
    load_ns = int(payload.get("load_duration") or 0)
    return {
        "wall_ms": round(wall_ms, 2),
        "load_ms": round(load_ns / 1_000_000, 2),
        "time_to_first_token_ms": round(prompt_ns / 1_000_000, 2),
        "prompt_tokens": prompt_count,
        "output_tokens": output_count,
        "prompt_tokens_per_second": round(prompt_count / (prompt_ns / 1_000_000_000), 2)
        if prompt_ns
        else None,
        "output_tokens_per_second": round(output_count / (output_ns / 1_000_000_000), 2)
        if output_ns
        else None,
    }


async def _ollama_chat(
    messages: list[dict[str, str]],
    *,
    model: str,
    temperature: float,
    num_predict: int,
    num_ctx: int,
    response_format: dict[str, Any] | str = "json",
) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "think": False,
                "format": response_format,
                "options": {
                    "temperature": temperature,
                    "num_predict": num_predict,
                    "num_ctx": num_ctx,
                },
            },
        )
    wall_ms = (time.perf_counter() - started) * 1000
    response.raise_for_status()
    return response.json(), wall_ms


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.model = INFERENCE_MODEL
    yield


app = FastAPI(
    title="Contexta Local Generative Inference Server",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            payload = response.json()
        names = [str(item.get("name", "")) for item in payload.get("models", [])]
        # Ollama reports fully-qualified names including the tag
        # ("contexta-lfm-extract:latest"), while the configured model is usually
        # untagged. An exact membership test therefore reported model_loaded
        # false on a perfectly healthy install, which is what made the console
        # show the extractor as unavailable. Compare on the untagged name.
        def _untagged(value: str) -> str:
            return value.split(":", 1)[0].strip()

        wanted = _untagged(app.state.model)
        loaded = any(_untagged(name) == wanted for name in names)
        return {
            "status": "healthy",
            "service": "contexta-inference-server",
            "backend": "ollama",
            "model": app.state.model,
            "model_loaded": loaded,
            "available_models": names,
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT,
            "chunk_sentences": CHUNK_SENTENCES,
        }
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Local inference backend unavailable: {exc}") from exc


@app.post("/v1/chat/completions", response_model=ChatResponse)
async def chat_completions(request: ChatRequest) -> ChatResponse:
    model = request.model or app.state.model
    try:
        payload, wall_ms = await _ollama_chat(
            [message.model_dump() for message in request.messages],
            model=model,
            temperature=request.temperature,
            num_predict=request.max_tokens,
            num_ctx=request.num_ctx,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Inference request failed: {exc}") from exc
    message = payload.get("message", {})
    return ChatResponse(
        id=str(payload.get("created_at", time.time())),
        model=model,
        content=str(message.get("content", "")),
        finish_reason=payload.get("done_reason"),
        metrics=_timings(payload, wall_ms),
    )


@app.post("/v1/extract", response_model=ExtractResponse)
async def extract(request: ExtractRequest) -> ExtractResponse:
    """Extract memories, chunking the conversation when it is long.

    A single request for a large conversation measurably loses facts even
    though the model has 128k of context and stops of its own accord. Splitting
    into segments recovers them. See ``contexta.core.extraction.chunking`` for
    the measurements.
    """
    model = request.model or app.state.model

    chunks = split_conversation(
        request.conversation,
        max_sentences=request.chunk_sentences,
        max_chars=request.chunk_max_chars,
    )
    if not chunks:
        chunks = [request.conversation]

    per_chunk_max_tokens = (
        request.max_tokens if len(chunks) == 1 else CHUNK_MAX_TOKENS
    )

    claim_groups: list[list[dict[str, Any]]] = []
    salvaged_chunks = 0
    failed_chunks = 0
    first_payload: dict[str, Any] = {}
    total_wall_ms = 0.0
    eval_count = 0

    for chunk in chunks:
        try:
            payload, wall_ms = await _ollama_chat(
                [
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": chunk},
                ],
                model=model,
                temperature=0.0,
                num_predict=per_chunk_max_tokens,
                num_ctx=request.num_ctx,
                response_format=memory_schema(),
            )
        except httpx.HTTPError as exc:
            # One failed chunk must not discard the ones that succeeded.
            failed_chunks += 1
            logger.warning(
                "extraction chunk %d/%d failed: %s",
                len(claim_groups) + 1,
                len(chunks),
                exc,
            )
            continue

        total_wall_ms += wall_ms
        eval_count += int(payload.get("eval_count") or 0)
        if not first_payload:
            first_payload = payload

        raw_content = str(payload.get("message", {}).get("content", ""))
        try:
            result = ExtractionEnvelope.model_validate_json(raw_content)
            claim_groups.append([c.model_dump() for c in result.memories])
        except ValueError:
            # The chunk still truncated. Recover whatever complete claims it
            # managed to emit rather than losing the whole segment.
            recovered, _was_partial = salvage_json_array(raw_content)
            if recovered:
                salvaged_chunks += 1
                claim_groups.append(recovered)
            else:
                failed_chunks += 1
                logger.warning(
                    "extraction chunk %d/%d produced no recoverable claims",
                    len(claim_groups) + 1,
                    len(chunks),
                )

    if not claim_groups:
        detail = (
            "Model returned no usable extraction JSON"
            + (" (every chunk failed)" if failed_chunks else "")
        )
        raise HTTPException(status_code=502, detail=detail)

    merged = merge_claims(claim_groups)
    merged.chunks = len(chunks)
    merged.salvaged_chunks = salvaged_chunks
    merged.failed_chunks = failed_chunks

    # Validate the merged set so callers keep the same contract as before.
    try:
        claims = [ExtractionClaim.model_validate(c).model_dump() for c in merged.claims]
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Model returned invalid extraction JSON: {exc}",
        ) from exc

    metrics = _timings(first_payload, total_wall_ms)
    metrics["eval_count"] = eval_count
    metrics["chunks"] = len(chunks)
    metrics["salvaged_chunks"] = salvaged_chunks
    metrics["failed_chunks"] = failed_chunks
    metrics["duplicate_claims"] = merged.duplicate_claims

    return ExtractResponse(
        model=model,
        claims=claims,
        raw_content=str(first_payload.get("message", {}).get("content", "")),
        metrics=metrics,
    )


__all__ = ["app"]
