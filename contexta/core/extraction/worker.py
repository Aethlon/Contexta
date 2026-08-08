"""LLM-backed memory extraction worker.

Converts validated observations into typed memory candidates. Later pipeline
tasks handle deduplication, entity resolution, scoring, and storage.
"""

import json
import logging
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from contexta.core.errors import ExtractionError
from contexta.core.extraction.sensitive_filter import secondary_scan
from contexta.core.schemas import ExtractedMemory, ObservationPayload
from contexta.core.types import MemoryType, SourceType
from contexta.services.llm import LLMError, LLMService

logger = logging.getLogger(__name__)


class ExtractionWorker:
    """Extract typed memories from observation payloads."""

    _SYSTEM_PROMPT = (
        "You extract durable memories for an AI agent. Return strict JSON with "
        "a top-level 'memories' array. Each item must include memory_type, "
        "source_type, title, content, and may include structured_data, tags, "
        "entities, has_emphasis, impacts_decisions."
    )

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self._llm = llm_service or LLMService()

    async def extract(self, payload: ObservationPayload) -> list[ExtractedMemory]:
        """Extract memories from a validated observation payload."""
        try:
            response = await self._llm.complete_json(
                prompt=self._build_prompt(payload),
                system_prompt=self._SYSTEM_PROMPT,
            )
        except LLMError as exc:
            logger.exception(
                "LLM extraction failed for session_id=%s user_id=%s",
                payload.session_id,
                payload.user_id,
            )
            raise ExtractionError(
                f"LLM extraction failed: {exc}",
                observation_id=str(payload.session_id),
            ) from exc

        memories = self._parse_memories(response, payload)
        safe_memories = [
            memory for memory in memories if not secondary_scan(memory.content)
        ]

        discarded = len(memories) - len(safe_memories)
        if discarded:
            logger.warning(
                "Discarded %d extracted memories containing sensitive data for session_id=%s",
                discarded,
                payload.session_id,
            )

        return safe_memories

    def _build_prompt(self, payload: ObservationPayload) -> str:
        """Build a compact extraction prompt from an observation."""
        prompt_payload = {
            "user_id": str(payload.user_id),
            "organization_id": str(payload.organization_id),
            "session_id": str(payload.session_id),
            "messages": payload.messages,
            "metadata": payload.metadata or {},
            "policy": payload.policy,
            "supported_memory_types": [memory_type.value for memory_type in MemoryType],
            "supported_source_types": [source_type.value for source_type in SourceType],
        }
        return json.dumps(prompt_payload, separators=(",", ":"))

    def _parse_memories(
        self,
        response: dict[str, Any],
        payload: ObservationPayload,
    ) -> list[ExtractedMemory]:
        """Validate LLM output into ExtractedMemory instances."""
        raw_memories = response.get("memories", [])
        if not isinstance(raw_memories, list):
            raise ExtractionError(
                "LLM extraction response must contain a memories array.",
                observation_id=str(payload.session_id),
            )

        memories: list[ExtractedMemory] = []
        for index, item in enumerate(raw_memories):
            if not isinstance(item, dict):
                logger.warning(
                    "Skipping non-object extracted memory at index=%d session_id=%s",
                    index,
                    payload.session_id,
                )
                continue

            normalized = self._normalize_memory_item(item)
            try:
                memories.append(ExtractedMemory(**normalized))
            except PydanticValidationError as exc:
                logger.warning(
                    "Skipping invalid extracted memory at index=%d session_id=%s errors=%s",
                    index,
                    payload.session_id,
                    exc.errors(),
                )

        return memories

    def _normalize_memory_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Apply conservative defaults before schema validation."""
        normalized = dict(item)
        normalized.setdefault("memory_type", MemoryType.CUSTOM.value)
        normalized.setdefault("source_type", SourceType.AGENT_INFERENCE.value)
        normalized.setdefault("structured_data", None)
        normalized.setdefault("tags", [])
        normalized.setdefault("entities", [])
        normalized.setdefault("has_emphasis", False)
        normalized.setdefault("impacts_decisions", False)

        title = str(normalized.get("title") or "").strip()
        content = str(normalized.get("content") or "").strip()
        if not title and content:
            title = content[:80].strip()

        normalized["title"] = title
        normalized["content"] = content
        return normalized
