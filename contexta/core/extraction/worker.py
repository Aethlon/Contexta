"""LLM-backed memory extraction worker.

Converts validated observations into typed memory candidates. Later pipeline
tasks handle deduplication, entity resolution, scoring, and storage.
"""

import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from contexta.core.errors import ExtractionError
from contexta.core.extraction.pii_filter import TIER_DIRECT, PiiFilter
from contexta.core.extraction.sensitive_filter import redact_all, secondary_redact
from contexta.core.extraction.tables import (
    AtomicAssignmentCandidate,
    MarkdownTable,
    parse_markdown_tables,
)
from contexta.core.schemas import ExtractedMemory, ObservationPayload
from contexta.core.temporal import (
    TemporalMessageContext,
    context_from_message,
    normalize_temporal_messages,
    normalize_temporal_text,
)
from contexta.core.types import MemoryType, SourceType
from contexta.services.llm import LLMError, LLMService, infer_memory_type

logger = logging.getLogger(__name__)


def _word_set(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_json_default))


def _source_text(value: Mapping[str, Any]) -> str | None:
    for key in ("original_text", "original_content", "content", "text"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _table_payload(
    table: MarkdownTable,
    *,
    source_id: Any = None,
    message_id: Any = None,
) -> dict[str, Any]:
    payload = table.model_dump(mode="json")
    payload["headers"] = table.headers
    payload["records"] = _json_safe(table.records)
    payload["row_count"] = table.row_count
    payload["column_count"] = table.column_count
    payload["source_id"] = str(source_id) if source_id is not None else table.source_id
    payload["message_id"] = str(message_id) if message_id is not None else table.message_id
    payload["source_message_id"] = payload["message_id"] or table.source_message_id
    return payload


def _candidate_payload(
    candidate: AtomicAssignmentCandidate,
    *,
    source_id: Any = None,
    message_id: Any = None,
) -> dict[str, Any]:
    payload = candidate.model_dump(mode="json")
    payload["source_id"] = str(source_id) if source_id is not None else candidate.source_id
    payload["message_id"] = str(message_id) if message_id is not None else candidate.message_id
    payload["source_message_id"] = payload["message_id"] or candidate.source_message_id
    return payload


def _merge_unique_dicts(
    existing: Any,
    generated: list[dict[str, Any]],
    *,
    identity: tuple[str, ...],
) -> list[dict[str, Any]]:
    values = [dict(value) for value in existing if isinstance(value, dict)] if isinstance(existing, list) else []
    seen = {
        json.dumps({key: value.get(key) for key in identity}, sort_keys=True, default=_json_default)
        for value in values
    }
    for value in generated:
        key = json.dumps({name: value.get(name) for name in identity}, sort_keys=True, default=_json_default)
        if key in seen:
            continue
        values.append(value)
        seen.add(key)
    return values


def _merge_unique_values(existing: Any, generated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = [dict(value) for value in existing if isinstance(value, dict)] if isinstance(existing, list) else []
    seen = {json.dumps(value, sort_keys=True, default=_json_default) for value in values}
    for value in generated:
        key = json.dumps(value, sort_keys=True, default=_json_default)
        if key in seen:
            continue
        values.append(value)
        seen.add(key)
    return values


def _safe_timezone(value: Any, fallback: str = "UTC") -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None and value.utcoffset() is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.endswith(("Z", "z")):
            candidate = f"{candidate[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else parsed.replace(tzinfo=UTC)
    return None


def _source_message_text(message: Mapping[str, Any]) -> str | None:
    for key in ("original_text", "original_content", "content", "text"):
        value = message.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, list):
            parts: list[str] = []
            for block in value:
                if isinstance(block, Mapping):
                    candidate = block.get("text") or block.get("content")
                else:
                    candidate = block
                if isinstance(candidate, str):
                    parts.append(candidate)
            if parts:
                return "\n".join(parts)
    return None


def _message_identifier(message: Mapping[str, Any], payload: ObservationPayload, key: str) -> str | None:
    value = message.get(key)
    if value is None and key == "message_id":
        value = message.get("source_message_id")
    if value is None:
        value = (
            payload.message_id or payload.source_message_id
            if key == "message_id"
            else payload.source_id
        )

    return str(value) if value is not None else None


def _context_message(
    item: Mapping[str, Any],
    payload: ObservationPayload,
    normalized_messages: list[dict[str, Any]],
) -> tuple[Mapping[str, Any] | None, TemporalMessageContext | None]:
    requested_id = item.get("message_id") or item.get("source_message_id")
    if requested_id is not None:
        requested = str(requested_id)
        for message in normalized_messages:
            context = context_from_message(message)
            if context.message_id == requested or context.source_id == requested:
                return message, context

    contexts = [context_from_message(message) for message in normalized_messages]
    reference_pairs = [(index, context) for index, context in enumerate(contexts) if context.reference_at is not None]
    if not reference_pairs:
        if len(contexts) == 1:
            return normalized_messages[0], contexts[0]
        return None, None

    references = {context.reference_at.isoformat() for _, context in reference_pairs if context.reference_at is not None}
    if len(references) == 1:
        index, context = reference_pairs[0]
        return normalized_messages[index], context

    content_words = _word_set(str(item.get("content") or item.get("original_text") or ""))
    scored: list[tuple[int, int, int, TemporalMessageContext]] = []
    for index, context in reference_pairs:
        message_words = _word_set(context.normalized_text or context.original_text or "")
        score = len(content_words & message_words)
        scored.append((score, -index, index, context))
    scored.sort(key=lambda value: (value[0], value[1]), reverse=True)
    if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        index, context = scored[0][2], scored[0][3]
        return normalized_messages[index], context
    return None, None


def _title_cased(value: str) -> str:
    """Render a name in the casing the soft-name pattern recognises.

    "  fatima   OKAFOR " and "Fatima Okafor" name one entity but only the second
    matches the pattern, so only the second would be pseudonymized.
    """
    return " ".join(word.capitalize() for word in value.split())


def _redact_leaves(value: Any) -> Any:
    """Rewrite every string leaf of a JSON-ish value through the redaction gate."""
    if isinstance(value, str):
        return redact_all(value).redacted_content
    if isinstance(value, list):
        return [_redact_leaves(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _redact_leaves(item) for key, item in value.items()}
    return value


def _fact_text(value: Any) -> str | None:
    """Coerce one component of a structured fact to a trimmed string."""
    if value is None or isinstance(value, (Mapping, list, tuple, set, bool)):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def normalize_structured_fact(item: dict[str, Any]) -> dict[str, Any] | None:
    """Lift a subject/predicate/object triple out of an LLM memory item.

    The triple is what makes a fact slot nameable: subject+predicate identify
    *which* fact is being asserted and object is the value that can later be
    corrected, so a rephrasing keeps its slot while a new value supersedes it.

    Accepts the fact nested under `structured_data.fact`, or emitted at the top
    level as `fact`/`structured_fact`, because models move it between the two.
    Also accepts the triple as bare siblings of `structured_data` -- the shape
    the fine-tuned extractor actually emits (`{"subject": ..., "object": ...}`
    alongside `status`/`polarity`/`temporal`), which the nested-only lookup
    silently missed, leaving every structural key dead.
    Returns None unless subject, predicate and object are all present: a partial
    triple cannot name a slot, and guessing one would let an unrelated memory
    collide with a stored fact. The caller then falls back to the legacy
    text-hash key, so an omitted or malformed fact degrades rather than drops.
    """
    structured = item.get("structured_data")
    raw: Any = None
    for candidate in (structured if isinstance(structured, Mapping) else None, item):
        if not isinstance(candidate, Mapping):
            continue
        for key in ("fact", "structured_fact"):
            value = candidate.get(key)
            if isinstance(value, Mapping):
                raw = value
                break
        if raw is not None:
            break
    if raw is None:
        triple = ("subject", "predicate", "object")
        for candidate in (structured if isinstance(structured, Mapping) else None, item):
            if isinstance(candidate, Mapping) and all(name in candidate for name in triple):
                raw = candidate
                break
    if raw is None:
        return None

    fact: dict[str, str] = {}
    for name in ("subject", "predicate", "object", "context"):
        value = _fact_text(raw.get(name))
        if value is not None:
            fact[name] = value
    if not {"subject", "predicate", "object"}.issubset(fact):
        return None
    return fact


class ExtractionWorker:
    """Extract typed memories from observation payloads."""

    _SYSTEM_PROMPT = (
        "You extract durable memories for an AI agent. Return strict JSON with "
        "a top-level 'memories' array. Each item must include memory_type, "
        "source_type, title, content, and may include structured_data, tags, "
        "entities, has_emphasis, impacts_decisions, event_at, observed_at, "
        "temporal_precision, temporal_basis. The 'entities' field, if "
        "present, MUST be a flat JSON array of plain strings (entity names "
        "only, e.g. [\"Caroline\", \"LGBTQ support group\"]) -- never objects "
        "and never nested structures."
    )

    _FACT_PROMPT = (
        " When the memory asserts one checkable thing about one subject, also "
        "emit it as structured_data.fact = {\"subject\": ..., \"predicate\": ..., "
        "\"object\": ..., \"context\": ...}. 'subject' is the entity the fact is "
        "about (\"Fatima Okafor\"), 'predicate' is the attribute in snake_case "
        "(\"lives_in\", \"employer\", \"preferred_language\"), 'object' is the value "
        "(\"Lisbon\"), and 'context' is an optional short qualifier. subject and "
        "predicate together name the fact; object is the value that may later be "
        "corrected. Emit the fact ONLY for a single checkable fact, and use the "
        "same subject/predicate wording for the same attribute so an update is "
        "recognised as the same fact."
    )

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self._llm = llm_service or LLMService()

    async def extract(
        self,
        payload: ObservationPayload,
        cortex_decision: Any = None,
    ) -> list[ExtractedMemory]:
        """Extract memories from a validated observation payload.

        Optionally accepts advisory guidance from Contexta Cortex without altering
        the extractor's internal parsing or output schema.
        """
        normalized_messages = self._normalize_messages(payload)
        json_kwargs = self._json_mode_kwargs(
            self._llm.complete_json, self._extraction_json_schema()
        )
        try:
            response = await self._llm.complete_json(
                prompt=self._build_prompt(
                    payload,
                    cortex_decision=cortex_decision,
                    normalized_messages=normalized_messages,
                ),
                system_prompt=self._SYSTEM_PROMPT + self._FACT_PROMPT,
                **json_kwargs,
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

        memories = self._parse_memories(
            response,
            payload,
            normalized_messages=normalized_messages,
        )
        # A direct identifier surviving extraction means the model reconstructed one,
        # so that memory is dropped. Soft identifiers are pseudonymized in place:
        # discarding every memory that names a person would gut the entity graph.
        safe_memories: list = []
        for memory in memories:
            must_discard, redacted = secondary_redact(memory.content)
            if must_discard:
                continue
            if redacted != memory.content:
                memory.content = redacted
            self._pseudonymize_structured_fact(memory)
            self._redact_structured_leaves(memory)
            safe_memories.append(memory)

        discarded = len(memories) - len(safe_memories)
        if discarded:
            logger.warning(
                "Discarded %d extracted memories containing sensitive data for session_id=%s",
                discarded,
                payload.session_id,
            )

        return safe_memories

    @staticmethod
    def _redact_structured_leaves(memory: Any) -> None:
        """Redact every string leaf of `structured_data` before it is persisted.

        Only `content` was being rewritten, but `structured_data` is stored
        verbatim and carries verbatim copies of the source text:
        `temporal.original_text` / `temporal.normalized_text`, and the
        `original_text` of every parsed table row. A memory whose prose was
        pseudonymized to `[PERSON_1]` therefore kept the real name beside it in
        the same row. Leaves are redacted in place rather than the memory being
        dropped, because the prose was already judged clean.

        This runs after `_pseudonymize_structured_fact` so the triple is not
        rescanned and given a second, different token.
        """
        structured = getattr(memory, "structured_data", None)
        if structured is None:
            return
        if isinstance(structured, dict):
            structured.update(_redact_leaves(structured))
        for attribute in ("title", "original_text", "normalized_text"):
            value = getattr(memory, attribute, None)
            if isinstance(value, str) and value:
                setattr(memory, attribute, redact_all(value).redacted_content)

    @staticmethod
    def _pseudonymize_structured_fact(memory: Any) -> None:
        """Pseudonymize a structured fact with the same tokens as the content.

        The prose is redacted before persistence but `structured_data` is written
        verbatim, so a real name in the fact subject would sit in the row while the
        sentence beside it reads `[PERSON_1]`. One scan over the already-redacted
        prose followed by the fact components reuses the tokens the prose scan
        assigns -- the prose is scanned first, so a name present in both resolves
        to the same token -- and a name only in the triple takes the next free
        index instead of colliding with an existing one.

        A direct-tier finding inside a fact component drops the triple: the
        component has no safe stable form, and keeping it would either store the
        value or collapse every such fact onto one indistinguishable value. The
        memory is still stored, on the legacy text-hash key.
        """
        structured = getattr(memory, "structured_data", None)
        if not isinstance(structured, dict):
            return
        fact = structured.get("fact")
        if not isinstance(fact, dict):
            return
        components = [value for value in fact.values() if isinstance(value, str)]
        if not components:
            return

        scan_input = "\n".join([memory.content or "", memory.title or "", *components])
        result = PiiFilter().scan(scan_input)
        if any(finding.tier == TIER_DIRECT for finding in result.findings):
            structured.pop("fact", None)
            structured.pop("fact_value", None)
            return

        # The soft-name pattern only matches Capitalised Capitalised text, so a
        # subject the model wrote as "  fatima   OKAFOR " escapes pseudonymization
        # while the prose beside it is redacted. The same person would then reach
        # storage twice under two spellings and split one fact slot in two, so the
        # subject is also offered to the scan in its canonical casing.
        extra = _title_cased(fact["subject"]) if isinstance(fact.get("subject"), str) else ""
        if extra:
            extra_result = PiiFilter().scan(extra)
            if any(finding.tier == TIER_DIRECT for finding in extra_result.findings):
                structured.pop("fact", None)
                structured.pop("fact_value", None)
                return
            result.pseudonym_map = {**result.pseudonym_map, **extra_result.pseudonym_map}

        pseudonyms = result.pseudonym_map
        rewritten = {
            name: pseudonyms.get(value.strip().casefold(), value)
            for name, value in fact.items()
        }
        if isinstance(fact.get("subject"), str):
            canonical = _title_cased(fact["subject"])
            token = pseudonyms.get(canonical.casefold())
            if token is not None:
                rewritten["subject"] = token
        if rewritten == fact:
            return
        fact.update(rewritten)
        structured["fact"] = fact
        if isinstance(fact.get("object"), str):
            structured["fact_value"] = fact["object"]

    def _build_prompt(
        self,
        payload: ObservationPayload,
        cortex_decision: Any = None,
        normalized_messages: list[dict[str, Any]] | None = None,    ) -> str:
        """Build a compact extraction prompt from an observation."""
        if normalized_messages is None:
            normalized_messages = self._normalize_messages(payload)
        prompt_payload: dict[str, Any] = {
            "user_id": str(payload.user_id),
            "organization_id": str(payload.organization_id),
            "session_id": str(payload.session_id),
            "messages": normalized_messages,
            "metadata": payload.metadata or {},
            "policy": payload.policy,
            "supported_memory_types": [memory_type.value for memory_type in MemoryType],
            "supported_source_types": [source_type.value for source_type in SourceType],
        }
        if payload.occurred_at is not None:
            prompt_payload["occurred_at"] = payload.occurred_at
        if payload.observed_at is not None:
            prompt_payload["observed_at"] = payload.observed_at
        for field_name in ("event_at", "event_start", "event_end", "temporal_precision", "temporal_basis", "source_span"):
            field_value = getattr(payload, field_name, None)
            if field_value is not None:
                prompt_payload[field_name] = field_value
        if payload.source_id is not None:
            prompt_payload["source_id"] = str(payload.source_id)
        if payload.message_id is not None:
            prompt_payload["message_id"] = str(payload.message_id)
        if payload.source_message_id is not None:
            prompt_payload["source_message_id"] = str(payload.source_message_id)
        if payload.timezone is not None:
            prompt_payload["timezone"] = payload.timezone
        if payload.original_text is not None:
            prompt_payload["original_text"] = payload.original_text
        if payload.normalized_text is not None:
            prompt_payload["normalized_text"] = payload.normalized_text
        if cortex_decision is not None and getattr(cortex_decision, "suggested_memory_type", None):
            prompt_payload["cortex_hint"] = {
                "suggested_type": cortex_decision.suggested_memory_type,
                "is_update": getattr(cortex_decision, "is_update", False),
                "depth": getattr(cortex_decision, "extraction_depth", "normal"),
            }
        return json.dumps(prompt_payload, separators=(",", ":"), default=_json_default)

    def _normalize_messages(self, payload: ObservationPayload) -> list[dict[str, Any]]:
        metadata = payload.metadata if isinstance(payload.metadata, Mapping) else {}
        timezone = payload.timezone or metadata.get("timezone") or metadata.get("source_timezone")
        arguments = {
            "occurred_at": payload.occurred_at or metadata.get("occurred_at"),
            "observed_at": payload.observed_at or metadata.get("observed_at"),
            "source_id": payload.source_id or metadata.get("source_id"),
            "message_id": (
                payload.message_id
                or payload.source_message_id
                or metadata.get("message_id")
                or metadata.get("source_message_id")
            ),
        }
        if payload.event_start is not None:
            arguments["occurred_at"] = arguments["occurred_at"] or payload.event_start
        if payload.event_at is not None:
            arguments["occurred_at"] = arguments["occurred_at"] or payload.event_at
        try:
            return normalize_temporal_messages(payload.messages, timezone=timezone, **arguments)
        except ValueError:
            return normalize_temporal_messages(payload.messages, timezone="UTC", **arguments)

    def _parse_memories(
        self,
        response: dict[str, Any],
        payload: ObservationPayload,
        normalized_messages: list[dict[str, Any]] | None = None,
    ) -> list[ExtractedMemory]:
        """Validate LLM output into ExtractedMemory instances."""
        if normalized_messages is None:
            normalized_messages = self._normalize_messages(payload)
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
            normalized = self._apply_temporal_metadata(
                normalized,
                payload,
                normalized_messages,
            )
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

    def _context_for_memory(
        self,
        item: Mapping[str, Any],
        payload: ObservationPayload,
        normalized_messages: list[dict[str, Any]],
    ) -> TemporalMessageContext | None:
        _, context = _context_message(item, payload, normalized_messages)
        if context is not None:
            return context

        metadata = payload.metadata if isinstance(payload.metadata, Mapping) else {}
        occurred_at = payload.occurred_at or metadata.get("occurred_at")
        observed_at = payload.observed_at or metadata.get("observed_at")
        reference = occurred_at or observed_at
        if reference is None:
            return None
        basis = "payload_occurred_at" if occurred_at is not None else "payload_observed_at"
        source_id = payload.source_id or metadata.get("source_id")
        message_id = payload.message_id or payload.source_message_id or metadata.get("message_id") or metadata.get("source_message_id")
        return TemporalMessageContext(
            reference_at=reference,
            occurred_at=occurred_at,
            observed_at=observed_at,
            source_id=str(source_id) if source_id is not None else None,
            message_id=str(message_id) if message_id is not None else None,
            timezone=_safe_timezone(payload.timezone or metadata.get("timezone")),
            temporal_basis=basis,
        )

    def _apply_temporal_metadata(
        self,
        item: dict[str, Any],
        payload: ObservationPayload,
        normalized_messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        result = dict(item)
        source_message, context = _context_message(result, payload, normalized_messages)
        if context is None:
            context = self._context_for_memory(result, payload, normalized_messages)
        if result.get("source_id") is None:
            source_id = context.source_id if context is not None else payload.source_id
            result["source_id"] = str(source_id) if source_id is not None else None
        if result.get("message_id") is None:
            message_id = context.message_id if context is not None else payload.message_id
            result["message_id"] = str(message_id) if message_id is not None else None
        if result.get("source_message_id") is None:
            result["source_message_id"] = result.get("message_id")

        timezone = _safe_timezone(
            result.get("timezone")
            or result.get("event_timezone")
            or (context.timezone if context is not None else None)
            or payload.timezone
        )
        raw_content = result.get("original_text")
        if not isinstance(raw_content, str):
            raw_content = str(result.get("content") or "")
        raw_title = result.get("original_title")
        if not isinstance(raw_title, str):
            raw_title = str(result.get("title") or "")

        reference = context.reference_at if context is not None else None
        if reference is None:
            metadata = payload.metadata if isinstance(payload.metadata, Mapping) else {}
            reference = _as_datetime(
                result.get("event_start")
                or result.get("event_at")
                or payload.event_at
                or payload.occurred_at
                or metadata.get("occurred_at")
                or payload.observed_at
                or metadata.get("observed_at")
            )

        try:
            normalized_content = normalize_temporal_text(raw_content, reference, timezone)
        except ValueError:
            normalized_content = normalize_temporal_text(raw_content, reference, "UTC")
            timezone = "UTC"
        try:
            normalized_title = normalize_temporal_text(raw_title, reference, timezone)
        except ValueError:
            normalized_title = normalize_temporal_text(raw_title, reference, "UTC")
            timezone = "UTC"

        result["content"] = normalized_content.normalized_text
        result["title"] = normalized_title.normalized_text
        if result.get("original_text") is None:
            result["original_text"] = raw_content
        if result.get("normalized_text") is None or result.get("normalized_text") == raw_content:
            result["normalized_text"] = normalized_content.normalized_text
        if result.get("original_title") is None:
            result["original_title"] = raw_title
        if result.get("normalized_title") is None or result.get("normalized_title") == raw_title:
            result["normalized_title"] = normalized_title.normalized_text

        matches: list[Any] = []
        seen_matches: set[tuple[str, ...]] = set()
        for match in [*normalized_content.matches, *normalized_title.matches, *(context.matches if context is not None else [])]:
            resolved = match.resolved_at.isoformat() if match.resolved_at is not None else ""
            span = match.source_span or {}
            identity = (match.original_expression, str(span.get("start")), str(span.get("end")), resolved)
            if identity not in seen_matches:
                seen_matches.add(identity)
                matches.append(match)
        resolved_matches = [match for match in matches if match.resolved_at is not None]

        raw_observed_at = result.get("observed_at")
        observed_at = _as_datetime(raw_observed_at)
        if observed_at is None and context is not None:
            observed_at = context.observed_at
        if observed_at is None:
            observed_at = datetime.now(UTC)
        result["observed_at"] = observed_at

        raw_event_at = result.get("event_at")
        event_at_value = _as_datetime(raw_event_at)
        raw_event_start = result.get("event_start")
        event_start_value = _as_datetime(raw_event_start)
        raw_event_end = result.get("event_end")
        event_end_value = _as_datetime(raw_event_end)
        selected_match = resolved_matches[0] if resolved_matches else None

        if event_start_value is not None:
            event_start = event_start_value
            event_at = event_at_value or event_start_value
            precision = result.get("temporal_precision") or "exact"
            basis = result.get("temporal_basis") or "extracted_event_interval"
        elif event_at_value is not None:
            event_start = event_at_value
            event_at = event_at_value
            precision = result.get("temporal_precision") or "exact"
            basis = result.get("temporal_basis") or "extracted_event_at"
        elif selected_match is not None:
            event_start = selected_match.event_start or selected_match.resolved_at
            event_at = selected_match.resolved_at or event_start
            event_end_value = selected_match.event_end
            precision = result.get("temporal_precision") or selected_match.temporal_precision
            basis = result.get("temporal_basis") or selected_match.temporal_basis
        elif context is not None and (context.event_start is not None or context.reference_at is not None):
            event_start = context.event_start or context.reference_at
            event_at = event_start
            event_end_value = context.event_end
            precision = result.get("temporal_precision") or context.temporal_precision or "exact"
            basis = result.get("temporal_basis") or context.temporal_basis
        else:
            event_start = None
            event_at = None
            precision = result.get("temporal_precision") or "unknown"
            basis = result.get("temporal_basis") or "ingestion_fallback"

        if raw_event_end is not None and event_end_value is None:
            event_end_value = raw_event_end
        result["event_at"] = event_at
        result["event_start"] = event_start
        result["event_end"] = event_end_value
        result["timezone"] = timezone
        result["event_timezone"] = timezone
        result["temporal_precision"] = precision
        result["temporal_basis"] = basis

        source_span = result.get("source_span")
        if not isinstance(source_span, Mapping):
            source_span = selected_match.source_span if selected_match is not None else None
        if not isinstance(source_span, Mapping) and context is not None:
            source_span = context.source_span
        if isinstance(source_span, Mapping):
            span_value = {
                "start": source_span.get("start"),
                "end": source_span.get("end"),
            }
        else:
            span_value = None
        if result.get("source_start") is None and span_value is not None:
            result["source_start"] = span_value["start"]
        if result.get("source_end") is None and span_value is not None:
            result["source_end"] = span_value["end"]
        if result.get("source_span") is None and span_value is not None:
            result["source_span"] = span_value

        expression_payloads = [
            {
                "original": match.original_expression,
                "normalized": match.normalized_expression,
                "resolved": match.resolved_at.isoformat() if match.resolved_at else None,
                "end": match.event_end.isoformat() if match.event_end else None,
                "precision": match.temporal_precision,
                "basis": match.temporal_basis,
                "timezone": match.timezone or timezone,
                "source_id": context.source_id if context is not None else result.get("source_id"),
                "message_id": context.message_id if context is not None else result.get("message_id"),
                "source_start": match.source_start,
                "source_end": match.source_end,
                "source_span": match.source_span,
            }
            for match in matches
        ]
        structured_data = result.get("structured_data")
        structured = dict(structured_data) if isinstance(structured_data, Mapping) else {}
        if expression_payloads:
            structured["temporal_expressions"] = _merge_unique_dicts(
                structured.get("temporal_expressions"),
                expression_payloads,
                identity=("original", "source_start", "source_end", "resolved"),
            )

        if context is not None:
            temporal_source = structured.get("temporal_source")
            temporal_source = dict(temporal_source) if isinstance(temporal_source, Mapping) else {}
            temporal_source.setdefault(
                "reference_at",
                context.reference_at.isoformat() if context.reference_at else None,
            )
            temporal_source.setdefault(
                "occurred_at",
                context.occurred_at.isoformat() if context.occurred_at else None,
            )
            temporal_source.setdefault(
                "observed_at",
                context.observed_at.isoformat() if context.observed_at else None,
            )
            temporal_source.setdefault("source_id", context.source_id)
            temporal_source.setdefault("message_id", context.message_id)
            temporal_source.setdefault("basis", context.temporal_basis)
            temporal_source.setdefault("timezone", context.timezone)
            temporal_source.setdefault("source_span", context.source_span)
            structured["temporal_source"] = temporal_source

        temporal = structured.get("temporal")
        temporal = dict(temporal) if isinstance(temporal, Mapping) else {}
        temporal.setdefault("event_at", event_at.isoformat() if event_at is not None else None)
        temporal.setdefault("event_start", event_start.isoformat() if event_start is not None else None)
        temporal.setdefault("event_end", event_end_value.isoformat() if event_end_value is not None else None)
        temporal.setdefault("observed_at", observed_at.isoformat())
        temporal.setdefault("precision", precision)
        temporal.setdefault("temporal_precision", precision)
        temporal.setdefault("basis", basis)
        temporal.setdefault("temporal_basis", basis)
        temporal.setdefault("timezone", timezone)
        temporal.setdefault("source_span", span_value)
        temporal.setdefault("original_text", raw_content)
        temporal.setdefault("normalized_text", normalized_content.normalized_text)
        temporal.setdefault("matches", [dict(item) for item in expression_payloads])
        structured["temporal"] = temporal
        result["structured_data"] = structured

        temporal_value = result.get("temporal")
        temporal_value = dict(temporal_value) if isinstance(temporal_value, Mapping) else {}
        temporal_value.setdefault("event_at", event_at.isoformat() if event_at is not None else None)
        temporal_value.setdefault("event_start", event_start.isoformat() if event_start is not None else None)
        temporal_value.setdefault("event_end", event_end_value.isoformat() if event_end_value is not None else None)
        temporal_value.setdefault("precision", precision)
        temporal_value.setdefault("basis", basis)
        temporal_value.setdefault("timezone", timezone)
        temporal_value.setdefault("source_span", span_value)
        temporal_value.setdefault("original_text", raw_content)
        temporal_value.setdefault("normalized_text", normalized_content.normalized_text)
        result["temporal"] = temporal_value

        self._apply_table_metadata(
            result,
            payload,
            normalized_messages,
            source_message=source_message,
        )
        return result

    def _apply_table_metadata(
        self,
        result: dict[str, Any],
        payload: ObservationPayload,
        normalized_messages: list[dict[str, Any]],
        *,
        source_message: Mapping[str, Any] | None = None,
    ) -> None:
        messages = [source_message] if source_message is not None else normalized_messages
        if source_message is None and len(normalized_messages) == 1:
            messages = normalized_messages
        generated_tables: list[dict[str, Any]] = []
        generated_candidates: list[dict[str, Any]] = []
        generated_rows: list[dict[str, Any]] = []
        generated_table_rows: list[list[dict[str, Any]]] = []
        for message in messages:
            text = _source_message_text(message)
            if not text:
                continue
            source_id = _message_identifier(message, payload, "source_id")
            message_id = _message_identifier(message, payload, "message_id")
            for table in parse_markdown_tables(text, source_id=source_id, message_id=message_id):
                table_payload = _table_payload(table, source_id=source_id, message_id=message_id)
                generated_tables.append(table_payload)
                table_rows = _json_safe(table.records)
                generated_table_rows.append(table_rows)
                generated_rows.extend(table_rows)
                generated_candidates.extend(
                    _candidate_payload(candidate, source_id=source_id, message_id=message_id)
                    for candidate in table.assignment_candidates
                )

        content_text = result.get("original_text")
        if not isinstance(content_text, str) or not content_text:
            content_text = result.get("content")
        if isinstance(content_text, str) and content_text:
            source_id = result.get("source_id")
            message_id = result.get("message_id")
            for table in parse_markdown_tables(
                content_text,
                source_id=str(source_id) if source_id is not None else None,
                message_id=str(message_id) if message_id is not None else None,
            ):
                table_payload = _table_payload(
                    table,
                    source_id=source_id,
                    message_id=message_id,
                )
                generated_tables.append(table_payload)
                table_rows = _json_safe(table.records)
                generated_table_rows.append(table_rows)
                generated_rows.extend(table_rows)
                generated_candidates.extend(
                    _candidate_payload(
                        candidate,
                        source_id=source_id,
                        message_id=message_id,
                    )
                    for candidate in table.assignment_candidates
                )

        if not generated_tables:
            return

        result["tables"] = _merge_unique_dicts(
            result.get("tables"),
            generated_tables,
            identity=("table_id", "source_id", "message_id", "original_text", "source_span"),
        )
        result["assignment_candidates"] = _merge_unique_dicts(
            result.get("assignment_candidates"),
            generated_candidates,
            identity=("table_id", "table_index", "row_index", "column_index", "source_id", "message_id", "key"),
        )
        result["table_rows"] = _merge_unique_values(result.get("table_rows"), generated_rows)
        structured = result.get("structured_data")
        structured = dict(structured) if isinstance(structured, Mapping) else {}
        structured["tables"] = _merge_unique_dicts(
            structured.get("tables"),
            generated_tables,
            identity=("table_id", "source_id", "message_id", "original_text", "source_span"),
        )
        structured["assignment_candidates"] = _merge_unique_dicts(
            structured.get("assignment_candidates"),
            generated_candidates,
            identity=("table_id", "table_index", "row_index", "column_index", "source_id", "message_id", "key"),
        )
        structured["table_rows"] = _merge_unique_values(structured.get("table_rows"), generated_rows)
        if "table" not in structured and generated_tables:
            table = generated_tables[0]
            structured["table"] = {
                "columns": [column.get("name") for column in table.get("columns", []) if isinstance(column, dict)],
                "rows": generated_table_rows[0] if generated_table_rows else [],
                "source_id": table.get("source_id"),
                "message_id": table.get("message_id"),
            }
        if result.get("table") is None and isinstance(structured.get("table"), Mapping):
            result["table"] = dict(structured["table"])
        result["structured_data"] = structured

    @staticmethod
    def _json_mode_kwargs(method: Any, json_schema: dict[str, Any]) -> dict[str, Any]:
        """Pass `json_schema` only to an LLM service that declares it.

        `LLMService` is duck-typed throughout the codebase and in tests, so a
        new keyword must not be introduced unconditionally: a substitute
        implementation with the older signature would raise TypeError and take
        the whole extraction down.
        """
        import inspect

        try:
            parameters = inspect.signature(method).parameters
        except (TypeError, ValueError):
            return {}
        if "json_schema" in parameters or any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        ):
            return {"json_schema": json_schema}
        return {}

    @classmethod
    def _extraction_json_schema(cls) -> dict[str, Any]:
        """Schema for grammar-constrained decoding of the extraction response.

        Small local models drop commas and quotes on long generations, and
        repairing the text afterwards would risk persisting corrupted facts.
        Handing the provider this schema means the sampler can only emit a
        document that already satisfies it. Enum values are left as plain
        strings: constraining them here would reject the free-form labels
        `_normalize_memory_item` exists to coerce.
        """
        return {
            "type": "object",
            "properties": {
                "memories": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                            "memory_type": {"type": "string"},
                            "source_type": {"type": "string"},
                            "tags": {"type": "array", "items": {"type": "string"}},
                            "entities": {"type": "array", "items": {"type": "string"}},
                            "has_emphasis": {"type": "boolean"},
                            "impacts_decisions": {"type": "boolean"},
                            "structured_data": {
                                "type": "object",
                                "properties": {
                                    "fact": {
                                        "type": "object",
                                        "properties": {
                                            "subject": {"type": "string"},
                                            "predicate": {"type": "string"},
                                            "object": {"type": "string"},
                                            "context": {"type": "string"},
                                        },
                                        "required": ["subject", "predicate", "object"],
                                    }
                                },
                            },
                        },
                        "required": ["title", "content", "memory_type", "source_type"],
                    },
                }
            },
            "required": ["memories"],
        }

    def _normalize_memory_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Apply conservative coercion and defaults before schema validation."""
        normalized = dict(item)
        raw_title = normalized.get("title")
        raw_content = normalized.get("content")
        original_title = raw_title if isinstance(raw_title, str) else str(raw_title or "")
        original_content = raw_content if isinstance(raw_content, str) else str(raw_content or "")
        normalized.setdefault("structured_data", None)
        normalized.setdefault("event_at", None)
        normalized.setdefault("event_start", None)
        normalized.setdefault("event_end", None)
        normalized.setdefault("observed_at", None)
        normalized.setdefault("timezone", None)
        normalized.setdefault("event_timezone", None)

        title = original_title.strip()
        content = original_content.strip()
        if not title and content:
            title = content[:80].strip()

        normalized["title"] = title
        normalized["content"] = content
        normalized["memory_type"] = self._normalize_memory_type(
            normalized.get("memory_type"), content=content
        )
        normalized["source_type"] = self._normalize_source_type(normalized.get("source_type"))
        normalized["tags"] = self._normalize_str_list(normalized.get("tags"))
        normalized["entities"] = self._normalize_entities(normalized.get("entities"))
        normalized["has_emphasis"] = self._normalize_flag(normalized.get("has_emphasis"))
        normalized["impacts_decisions"] = self._normalize_flag(
            normalized.get("impacts_decisions")
        )
        # _apply_temporal_metadata prefers original_* over the derived title and
        # content, so leave the key absent when the model supplied nothing -- an
        # empty string here would overwrite the title derived from content.
        for key, original in (
            ("original_text", original_content),
            ("original_title", original_title),
        ):
            if not normalized.get(key) and not original:
                normalized.pop(key, None)
        if not normalized.get("normalized_text"):
            normalized["normalized_text"] = content
        if not normalized.get("normalized_title"):
            normalized["normalized_title"] = title
        self._apply_structured_fact(normalized)
        return normalized

    @staticmethod
    def _apply_structured_fact(item: dict[str, Any]) -> None:
        """Store the triple and the value truth maintenance compares on.

        `fact_value` is read by `contexta.core.truth.service.fact_value`, which
        both the deduplicator and the contradiction detector use, so without it a
        rephrasing of the same value reads as a contradiction and churns the
        current truth.
        """
        fact = normalize_structured_fact(item)
        if fact is None:
            return
        structured = item.get("structured_data")
        structured = dict(structured) if isinstance(structured, Mapping) else {}
        structured["fact"] = fact
        structured["fact_value"] = fact["object"]
        item["structured_data"] = structured

    def _normalize_entities(self, entities: Any) -> list[str]:
        """Coerce LLM entity output into a flat list of plain strings.

        LLMs sometimes return entity mentions as objects (e.g.
        ``{"name": "Caroline", "type": "person"}``) despite prompt
        instructions to return flat strings. Rather than let that fail
        schema validation and silently drop the entire memory, extract a
        usable name from common shapes and fall back to a string cast.
        """
        if not isinstance(entities, list):
            return []

        normalized: list[str] = []
        for entity in entities:
            if isinstance(entity, str):
                name = entity.strip()
            elif isinstance(entity, dict):
                name = str(
                    entity.get("name") or entity.get("entity") or entity.get("value") or ""
                ).strip()
            else:
                name = str(entity).strip()
            if name:
                normalized.append(name)
        return normalized

    # LLM label vocabularies drift from our enums even when the model is
    # instruction-tuned on our schema, so map the labels models actually emit
    # rather than discarding the memory on a validation error.
    _MEMORY_TYPE_SYNONYMS: dict[str, str] = {
        "travel": MemoryType.EVENT.value,
        "trip": MemoryType.EVENT.value,
        "location": MemoryType.EVENT.value,
        "learning": MemoryType.SKILL.value,
        "education": MemoryType.SKILL.value,
        "education/training": MemoryType.SKILL.value,
        "task": MemoryType.EVENT.value,
        "action": MemoryType.EVENT.value,
        "activity": MemoryType.EVENT.value,
        "conversation": MemoryType.EPISODIC.value,
        "message": MemoryType.EPISODIC.value,
        "chat": MemoryType.EPISODIC.value,
        "profile": MemoryType.FACT.value,
        "attribute": MemoryType.FACT.value,
        "demographic": MemoryType.FACT.value,
        "identity": MemoryType.CONTACT.value,
        "person": MemoryType.CONTACT.value,
        "contact": MemoryType.CONTACT.value,
        "plan": MemoryType.GOAL.value,
        "intention": MemoryType.GOAL.value,
        "todo": MemoryType.GOAL.value,
        "task/todo": MemoryType.GOAL.value,
        "requirement": MemoryType.CONSTRAINT.value,
        "policy": MemoryType.RULE.value,
        "regulation": MemoryType.RULE.value,
        "guideline": MemoryType.RULE.value,
        "insight": MemoryType.PATTERN.value,
        "observation": MemoryType.PATTERN.value,
        "summary": MemoryType.PATTERN.value,
        "technical": MemoryType.PROCEDURAL.value,
        "how-to": MemoryType.PROCEDURAL.value,
        "workflow": MemoryType.PROCEDURAL.value,
        "affection": MemoryType.RELATIONSHIP.value,
        "social": MemoryType.RELATIONSHIP.value,
        "like": MemoryType.PREFERENCE.value,
        "likes": MemoryType.PREFERENCE.value,
        "favorite": MemoryType.PREFERENCE.value,
    }

    _SOURCE_TYPE_SYNONYMS: dict[str, str] = {
        "personal": SourceType.USER_EXPLICIT.value,
        "user": SourceType.USER_EXPLICIT.value,
        "human": SourceType.USER_EXPLICIT.value,
        "explicit": SourceType.USER_EXPLICIT.value,
        "stated": SourceType.USER_EXPLICIT.value,
        "chat": SourceType.USER_EXPLICIT.value,
        "conversation": SourceType.USER_EXPLICIT.value,
        "assistant": SourceType.AGENT_INFERENCE.value,
        "inference": SourceType.AGENT_INFERENCE.value,
        "inferred": SourceType.AGENT_INFERENCE.value,
        "model": SourceType.AGENT_INFERENCE.value,
        "llm": SourceType.AGENT_INFERENCE.value,
        "extraction": SourceType.AGENT_INFERENCE.value,
        "tool": SourceType.TOOL_OUTPUT.value,
        "function": SourceType.TOOL_OUTPUT.value,
        "mcp": SourceType.TOOL_OUTPUT.value,
        "file": SourceType.IMPORTED_FILE.value,
        "document": SourceType.IMPORTED_FILE.value,
        "import": SourceType.IMPORTED_FILE.value,
        "upload": SourceType.IMPORTED_FILE.value,
        "api": SourceType.API.value,
        "http": SourceType.API.value,
        "webhook": SourceType.API.value,
        "sdk": SourceType.API.value,
    }

    @classmethod
    def _normalize_memory_type(cls, value: Any, *, content: str = "") -> str:
        """Coerce an LLM-supplied memory type to a valid MemoryType value.

        An absent label keeps the historical ``custom`` default. A label the
        model *did* supply but that is not in our vocabulary is mapped through
        the synonym table and then inferred from the memory text, so a
        mislabelled memory still classifies usefully instead of being dropped.
        """
        label = str(value or "").strip().lower()
        valid = {member.value for member in MemoryType}
        if label in valid:
            return label
        if not label:
            return MemoryType.CUSTOM.value
        mapped = cls._MEMORY_TYPE_SYNONYMS.get(label)
        if mapped in valid:
            return mapped
        if content:
            return infer_memory_type(content)
        return MemoryType.CUSTOM.value

    @classmethod
    def _normalize_source_type(cls, value: Any) -> str:
        """Coerce an LLM-supplied source type to a valid SourceType value.

        An absent label keeps the historical ``agent_inference`` default: the
        memory was produced by an extraction model, so that is the truthful
        provenance when the model did not state one.
        """
        label = str(value or "").strip().lower()
        valid = {member.value for member in SourceType}
        if label in valid:
            return label
        if not label:
            return SourceType.AGENT_INFERENCE.value
        return cls._SOURCE_TYPE_SYNONYMS.get(label, SourceType.AGENT_INFERENCE.value)

    @staticmethod
    def _normalize_flag(value: Any) -> bool:
        """Coerce a truthy LLM value to bool.

        Models frequently answer a boolean field with the reason it is true
        (a list or sentence) rather than ``true``.
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"true", "yes", "y", "1", "impact", "impacts"}
        if isinstance(value, (list, tuple, set, dict)):
            return bool(value)
        return False

    @classmethod
    def _normalize_str_list(cls, value: Any) -> list[str]:
        """Coerce a scalar or comma-joined string into a list of clean strings."""
        if value is None:
            return []
        if isinstance(value, str):
            parts = [part.strip() for part in re.split(r"[,;|]", value)]
            return [part for part in parts if part]
        if isinstance(value, (list, tuple, set)):
            out: list[str] = []
            for item in value:
                if isinstance(item, str):
                    text = item.strip()
                elif isinstance(item, dict):
                    text = str(
                        item.get("name") or item.get("value") or item.get("tag") or ""
                    ).strip()
                else:
                    text = str(item).strip()
                if text:
                    out.append(text)
            return out
        text = str(value).strip()
        return [text] if text else []

