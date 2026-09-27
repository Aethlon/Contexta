from __future__ import annotations

import hashlib
import inspect
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol

from contexta.models.consolidation import ConsolidatedObservation
from contexta.models.proposal import (
    AdmissionState,
    MemoryProposal,
    ProposalType,
    ProposalValidationState,
    RiskTier,
)


class ConsolidationError(ValueError):
    pass


class InvalidEvidenceError(ConsolidationError):
    pass


class ProposalNotReadyError(ConsolidationError):
    pass


class CanonicalWriterRequired(ConsolidationError):
    pass


PolicyViolation = ProposalNotReadyError


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _value_of(value: Any, enum_type: type[Enum], default: str | None = None) -> str | None:
    if isinstance(value, enum_type):
        return str(value.value)
    if value is None:
        return default
    normalized = str(value).strip().lower().replace("-", "_")
    try:
        return str(enum_type(normalized).value)
    except ValueError:
        return default


def _as_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, uuid.UUID)):
        return [value]
    if isinstance(value, Mapping):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _unique(values: Any) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in _as_sequence(values):
        marker = str(value)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


def _uuid_values(values: Any) -> list[uuid.UUID]:
    result: list[uuid.UUID] = []
    for value in _as_sequence(values):
        try:
            parsed = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        except (AttributeError, TypeError, ValueError):
            continue
        if parsed not in result:
            result.append(parsed)
    return result


def _string_values(values: Any) -> list[str]:
    result: list[str] = []
    for value in _as_sequence(values):
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _value(item: Any, *names: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        for name in names:
            if name in item and item[name] is not None:
                return item[name]
        return default
    for name in names:
        candidate = getattr(item, name, None)
        if candidate is not None:
            return candidate
    return default


@dataclass(frozen=True)
class EvidenceReference:
    id: Any
    kind: str = "memory"
    fact_key: str | None = None
    confidence: float | None = None
    text: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "id": str(self.id),
            "kind": self.kind,
        }
        if self.fact_key:
            value["fact_key"] = self.fact_key
        if self.confidence is not None:
            value["confidence"] = _confidence(self.confidence)
        if self.text:
            value["text"] = self.text
        if self.metadata:
            value["metadata"] = dict(self.metadata)
        return value


@dataclass(frozen=True)
class AdmissionDecision:
    action: str
    admitted: bool
    risk_tier: str
    validation_state: str
    reason: str
    evidence_count: int
    supporting_count: int
    requires_review: bool
    auto_apply: bool = False

    @property
    def status(self) -> str:
        return self.action

    @property
    def admission_state(self) -> str:
        if self.action == "admit":
            return AdmissionState.ADMITTED.value
        if self.action == "reject":
            return AdmissionState.REJECTED.value
        return AdmissionState.REVIEW.value

    @property
    def can_apply(self) -> bool:
        return False


class RiskTieredAdmissionPolicy:
    _default_risk = {
        ProposalType.FACT.value: RiskTier.LOW.value,
        ProposalType.SUMMARY.value: RiskTier.LOW.value,
        ProposalType.GAP.value: RiskTier.LOW.value,
        ProposalType.MERGE.value: RiskTier.MEDIUM.value,
        ProposalType.BLOCK_UPDATE.value: RiskTier.HIGH.value,
        ProposalType.SUPERSESSION.value: RiskTier.CRITICAL.value,
    }
    _default_confidence = {
        RiskTier.LOW.value: 0.65,
        RiskTier.MEDIUM.value: 0.80,
        RiskTier.HIGH.value: 0.90,
        RiskTier.CRITICAL.value: 0.95,
    }
    _default_evidence = {
        RiskTier.LOW.value: 1,
        RiskTier.MEDIUM.value: 2,
        RiskTier.HIGH.value: 2,
        RiskTier.CRITICAL.value: 3,
    }
    _default_supporting = {
        RiskTier.LOW.value: 1,
        RiskTier.MEDIUM.value: 2,
        RiskTier.HIGH.value: 2,
        RiskTier.CRITICAL.value: 3,
    }

    def __init__(
        self,
        *,
        minimum_confidence: Mapping[RiskTier | str, float] | None = None,
        minimum_evidence: Mapping[RiskTier | str, int] | None = None,
        minimum_supporting: Mapping[RiskTier | str, int] | None = None,
    ) -> None:
        self.minimum_confidence = {
            self._risk_key(key): float(value)
            for key, value in {**self._default_confidence, **(minimum_confidence or {})}.items()
        }
        self.minimum_evidence = {
            self._risk_key(key): max(1, int(value))
            for key, value in {**self._default_evidence, **(minimum_evidence or {})}.items()
        }
        self.minimum_supporting = {
            self._risk_key(key): max(1, int(value))
            for key, value in {**self._default_supporting, **(minimum_supporting or {})}.items()
        }

    @staticmethod
    def _risk_key(value: RiskTier | str) -> str:
        return value.value if isinstance(value, RiskTier) else str(value).lower()

    def risk_for(self, proposal_type: ProposalType | str) -> str:
        proposal = _value_of(proposal_type, ProposalType)
        if proposal is None:
            return RiskTier.HIGH.value
        return self._default_risk[proposal]

    def evaluate(
        self,
        proposal_type: ProposalType | str,
        confidence: float = 0.0,
        evidence_ids: Sequence[Any] = (),
        supporting_ids: Sequence[Any] = (),
        fact_keys: Sequence[Any] = (),
        risk_tier: RiskTier | str | None = None,
        evidence_count: int | None = None,
        supporting_count: int | None = None,
    ) -> AdmissionDecision:
        proposal = _value_of(proposal_type, ProposalType)
        if proposal is None:
            return self._decision(
                action="reject",
                risk=RiskTier.HIGH.value,
                validation_state=ProposalValidationState.REJECTED.value,
                reason="unsupported_proposal_type",
                evidence_count=0,
                supporting_count=0,
                requires_review=False,
            )
        risk = self._risk_key(risk_tier) if risk_tier is not None else self.risk_for(proposal)
        if risk not in self._default_confidence:
            risk = RiskTier.HIGH.value
        evidence = len(_unique(evidence_ids))
        supporting = len(_unique(supporting_ids))
        if evidence_count is not None:
            evidence = max(evidence, int(evidence_count))
        if supporting_count is not None:
            supporting = max(supporting, int(supporting_count))
        if evidence == 0:
            return self._decision(
                action="reject",
                risk=risk,
                validation_state=ProposalValidationState.REJECTED.value,
                reason="missing_evidence",
                evidence_count=evidence,
                supporting_count=supporting,
                requires_review=False,
            )
        if evidence < self.minimum_evidence[risk]:
            return self._decision(
                action="reject" if risk == RiskTier.CRITICAL.value else "review",
                risk=risk,
                validation_state=ProposalValidationState.NEEDS_REVIEW.value,
                reason="insufficient_evidence",
                evidence_count=evidence,
                supporting_count=supporting,
                requires_review=risk != RiskTier.CRITICAL.value,
            )
        if supporting < self.minimum_supporting[risk]:
            return self._decision(
                action="reject" if risk == RiskTier.CRITICAL.value else "review",
                risk=risk,
                validation_state=ProposalValidationState.NEEDS_REVIEW.value,
                reason="insufficient_supporting_references",
                evidence_count=evidence,
                supporting_count=supporting,
                requires_review=risk != RiskTier.CRITICAL.value,
            )
        score = _confidence(confidence)
        if score < self.minimum_confidence[risk]:
            return self._decision(
                action="review",
                risk=risk,
                validation_state=ProposalValidationState.NEEDS_REVIEW.value,
                reason="confidence_below_threshold",
                evidence_count=evidence,
                supporting_count=supporting,
                requires_review=True,
            )
        if risk != RiskTier.LOW.value:
            return self._decision(
                action="review",
                risk=risk,
                validation_state=ProposalValidationState.NEEDS_REVIEW.value,
                reason="high_risk_requires_review",
                evidence_count=evidence,
                supporting_count=supporting,
                requires_review=True,
            )
        return self._decision(
            action="admit",
            risk=risk,
            validation_state=ProposalValidationState.VALIDATED.value,
            reason="evidence_and_confidence_satisfied",
            evidence_count=evidence,
            supporting_count=supporting,
            requires_review=False,
        )

    decide = evaluate
    assess = evaluate

    @staticmethod
    def _decision(
        *,
        action: str,
        risk: str,
        validation_state: str,
        reason: str,
        evidence_count: int,
        supporting_count: int,
        requires_review: bool,
    ) -> AdmissionDecision:
        return AdmissionDecision(
            action=action,
            admitted=action in {"admit", "review"},
            risk_tier=risk,
            validation_state=validation_state,
            reason=reason,
            evidence_count=evidence_count,
            supporting_count=supporting_count,
            requires_review=requires_review,
            auto_apply=False,
        )


AdmissionPolicy = RiskTieredAdmissionPolicy


@dataclass(frozen=True)
class ConsolidationResult:
    observation: ConsolidatedObservation
    proposal: MemoryProposal
    admission: AdmissionDecision

    @property
    def accepted(self) -> bool:
        return self.admission.admitted

    @property
    def requires_review(self) -> bool:
        return self.admission.requires_review

    @property
    def can_apply(self) -> bool:
        return False


class ProposalStore(Protocol):
    async def insert_idempotently(
        self, record: MemoryProposal
    ) -> tuple[MemoryProposal, bool]: ...


class ObservationStore(Protocol):
    async def insert_idempotently(
        self, record: ConsolidatedObservation
    ) -> tuple[ConsolidatedObservation, bool]: ...


class CanonicalMemoryWriter(Protocol):
    async def apply_proposal(
        self,
        proposal: MemoryProposal,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> Any: ...


@dataclass(frozen=True)
class ApplyResult:
    proposal_id: uuid.UUID
    canonical_memory_id: uuid.UUID | None
    writer_result: Any


class CortexConsolidationService:
    def __init__(
        self,
        proposal_repository: Any,
        observation_repository: Any | None = None,
        *,
        policy: RiskTieredAdmissionPolicy | None = None,
        writer: CanonicalMemoryWriter | None = None,
    ) -> None:
        self._proposals = proposal_repository
        self._observations = observation_repository
        self._policy = policy or RiskTieredAdmissionPolicy()
        self._writer = writer

    @property
    def policy(self) -> RiskTieredAdmissionPolicy:
        return self._policy

    @property
    def proposal_repository(self) -> Any:
        return self._proposals

    @property
    def observation_repository(self) -> Any:
        return self._observations

    def evaluate_proposal(
        self,
        proposal_type: ProposalType | str,
        *,
        confidence: float = 0.0,
        evidence_ids: Sequence[Any] = (),
        supporting_ids: Sequence[Any] = (),
        fact_keys: Sequence[Any] = (),
        risk_tier: RiskTier | str | None = None,
    ) -> AdmissionDecision:
        return self._policy.evaluate(
            proposal_type,
            confidence=confidence,
            evidence_ids=evidence_ids,
            supporting_ids=supporting_ids,
            fact_keys=fact_keys,
            risk_tier=risk_tier,
        )

    async def create_proposal(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        proposal_type: ProposalType | str,
        payload: Mapping[str, Any] | None = None,
        evidence_ids: Sequence[Any] = (),
        supporting_ids: Sequence[Any] = (),
        fact_keys: Sequence[Any] = (),
        source_observation_ids: Sequence[Any] = (),
        target_memory_ids: Sequence[Any] = (),
        evidence_refs: Sequence[Mapping[str, Any] | EvidenceReference] = (),
        confidence: float | None = None,
        risk_tier: RiskTier | str | None = None,
        rationale: str = "",
        idempotency_key: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        consolidated_observation_id: uuid.UUID | None = None,
    ) -> MemoryProposal:
        proposal_name = _value_of(proposal_type, ProposalType) or str(proposal_type)
        evidence = _uuid_values(evidence_ids)
        support = _uuid_values([*supporting_ids, *evidence])
        sources = _uuid_values(source_observation_ids)
        targets = _uuid_values(target_memory_ids)
        facts = _string_values(fact_keys)
        references = [
            item.to_dict() if isinstance(item, EvidenceReference) else dict(item)
            for item in evidence_refs
        ]
        if not references and evidence:
            references = [{"id": str(item), "kind": "memory"} for item in evidence]
        score = self._score(
            confidence,
            [item.get("confidence") for item in references if item.get("confidence") is not None],
        )
        decision = self._policy.evaluate(
            proposal_name,
            confidence=score,
            evidence_ids=evidence,
            supporting_ids=support,
            fact_keys=facts,
            risk_tier=risk_tier,
        )
        key = idempotency_key or self._idempotency_key(
            organization_id=organization_id,
            user_id=user_id,
            proposal_type=proposal_name,
            payload=payload,
            evidence_ids=evidence,
            support_ids=support,
            fact_keys=facts,
        )
        errors: list[dict[str, Any]] = []
        if decision.action == "reject":
            errors.append({"code": decision.reason, "message": decision.reason})
        record = MemoryProposal(
            id=uuid.uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            consolidated_observation_id=consolidated_observation_id,
            proposal_type=proposal_name,
            risk_tier=decision.risk_tier,
            validation_state=decision.validation_state,
            admission_state=decision.admission_state,
            status="proposed" if decision.admitted else "rejected",
            idempotency_key=key,
            payload=dict(payload or {}),
            evidence_ids=evidence,
            fact_keys=facts,
            supporting_ids=support,
            source_observation_ids=sources,
            target_memory_ids=targets,
            evidence_refs=references,
            confidence=score,
            rationale=rationale or decision.reason,
            validation_errors=errors,
            metadata_=dict(metadata) if metadata is not None else None,
            updated_at=_utcnow(),
        )
        return await self._persist_proposal(record)

    propose = create_proposal

    async def _persist_proposal(self, record: MemoryProposal) -> MemoryProposal:
        method = getattr(self._proposals, "insert_idempotently", None)
        if method is not None:
            result = method(record)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, tuple):
                return result[0]
            return result
        method = getattr(self._proposals, "create_idempotently", None)
        if method is not None:
            result = method(record)
            return await result if inspect.isawaitable(result) else result
        method = getattr(self._proposals, "create", None)
        if method is None:
            raise ConsolidationError("A proposal repository is required.")
        result = method(record)
        return await result if inspect.isawaitable(result) else result

    async def _persist_observation(
        self, record: ConsolidatedObservation
    ) -> ConsolidatedObservation:
        if self._observations is None:
            return record
        method = getattr(self._observations, "insert_idempotently", None)
        if method is not None:
            result = method(record)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, tuple):
                return result[0]
            return result
        method = getattr(self._observations, "create_idempotently", None)
        if method is not None:
            result = method(record)
            return await result if inspect.isawaitable(result) else result
        method = getattr(self._observations, "create", None)
        if method is None:
            raise ConsolidationError("A consolidated observation repository is required.")
        result = method(record)
        return await result if inspect.isawaitable(result) else result

    @staticmethod
    def _score(confidence: float | None, reference_scores: Sequence[Any]) -> float:
        if confidence is not None:
            return _confidence(confidence)
        values = [_confidence(item) for item in reference_scores]
        if not values:
            return 0.0
        return sum(values) / len(values)

    @staticmethod
    def _idempotency_key(
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        proposal_type: str,
        payload: Mapping[str, Any] | None,
        evidence_ids: Sequence[uuid.UUID],
        support_ids: Sequence[uuid.UUID],
        fact_keys: Sequence[str],
    ) -> str:
        value = {
            "organization_id": str(organization_id),
            "user_id": str(user_id),
            "proposal_type": proposal_type,
            "payload": dict(payload or {}),
            "evidence_ids": [str(item) for item in evidence_ids],
            "support_ids": [str(item) for item in support_ids],
            "fact_keys": list(fact_keys),
        }
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        return f"cortex:proposal:{digest}"

    async def validate_proposal(
        self,
        proposal_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> MemoryProposal:
        del actor_id
        proposal = await self._get_proposal(proposal_id)
        if proposal is None:
            raise ConsolidationError("The proposal does not exist in the tenant.")
        decision = self._policy.evaluate(
            proposal.proposal_type,
            confidence=proposal.confidence,
            evidence_ids=proposal.evidence_ids or [],
            supporting_ids=proposal.supporting_ids or [],
            fact_keys=proposal.fact_keys or [],
            risk_tier=proposal.risk_tier,
        )
        method = getattr(self._proposals, "update_validation_state", None)
        if method is not None:
            await method(
                proposal_id,
                decision.validation_state,
                validation_errors=(
                    [{"code": decision.reason}] if decision.action == "reject" else []
                ),
            )
            return await self._get_proposal(proposal_id) or proposal
        proposal.validation_state = decision.validation_state
        proposal.admission_state = decision.admission_state
        proposal.updated_at = _utcnow()
        flush = getattr(self._proposals, "session", None)
        if flush is not None:
            await flush.flush()
        return proposal

    async def _get_proposal(self, proposal_id: uuid.UUID) -> MemoryProposal | None:
        method = getattr(self._proposals, "get_by_id", None)
        if method is None:
            raise ConsolidationError("A proposal repository is required.")
        result = method(proposal_id)
        return await result if inspect.isawaitable(result) else result

    async def consolidate(
        self,
        observations: Sequence[Any] | Mapping[str, Any] | None = None,
        *,
        evidence: Sequence[Any] | None = None,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        proposal_type: ProposalType | str = ProposalType.FACT,
        payload: Mapping[str, Any] | None = None,
        evidence_ids: Sequence[Any] = (),
        supporting_ids: Sequence[Any] = (),
        fact_keys: Sequence[Any] = (),
        source_observation_ids: Sequence[Any] = (),
        target_memory_ids: Sequence[Any] = (),
        confidence: float | None = None,
        risk_tier: RiskTier | str | None = None,
        idempotency_key: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ConsolidationResult:
        source = observations if observations is not None else evidence
        items = [source] if isinstance(source, Mapping) else list(source or [])
        extracted_refs, extracted_evidence, extracted_support, extracted_facts, texts = self._extract(
            items
        )
        evidence = _uuid_values([*extracted_evidence, *evidence_ids])
        support = _uuid_values([*extracted_support, *supporting_ids, *evidence])
        facts = _string_values([*extracted_facts, *fact_keys])
        proposal_name = _value_of(proposal_type, ProposalType) or str(proposal_type)
        decision = self._policy.evaluate(
            proposal_name,
            confidence=confidence or 0.0,
            evidence_ids=evidence,
            supporting_ids=support,
            fact_keys=facts,
            risk_tier=risk_tier,
        )
        base_key = idempotency_key or self._idempotency_key(
            organization_id=organization_id,
            user_id=user_id,
            proposal_type=proposal_name,
            payload=payload or {"texts": texts},
            evidence_ids=evidence,
            support_ids=support,
            fact_keys=facts,
        )
        content = self._content(payload, texts)
        score = self._score(
            confidence,
            [item.get("confidence") for item in extracted_refs if item.get("confidence") is not None],
        )
        if score == 0.0 and not texts and content:
            score = 0.0
        decision = self._policy.evaluate(
            proposal_name,
            confidence=score,
            evidence_ids=evidence,
            supporting_ids=support,
            fact_keys=facts,
            risk_tier=decision.risk_tier,
        )
        observation = ConsolidatedObservation(
            id=uuid.uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            observation_type=proposal_name,
            content=content,
            structured_data=dict(payload or {}),
            idempotency_key=base_key,
            risk_tier=decision.risk_tier,
            admission_state=decision.admission_state,
            validation_state=decision.validation_state,
            status="staged" if decision.admitted else "rejected",
            confidence=score,
            source_count=len(items),
            evidence_ids=evidence,
            supporting_ids=support,
            source_observation_ids=_uuid_values(source_observation_ids),
            fact_keys=facts,
            evidence_refs=extracted_refs
            or [{"id": str(item), "kind": "reference"} for item in evidence],
            metadata_=dict(metadata) if metadata is not None else None,
            updated_at=_utcnow(),
        )
        observation = await self._persist_observation(observation)
        proposal_key = base_key if idempotency_key else f"{base_key}:proposal"
        if len(proposal_key) > 255:
            proposal_key = f"cortex:proposal:{hashlib.sha256(proposal_key.encode()).hexdigest()}"
        proposal = await self.create_proposal(
            organization_id=organization_id,
            user_id=user_id,
            proposal_type=proposal_name,
            payload=payload,
            evidence_ids=evidence,
            supporting_ids=support,
            fact_keys=facts,
            source_observation_ids=source_observation_ids,
            target_memory_ids=target_memory_ids,
            evidence_refs=extracted_refs
            or [{"id": str(item), "kind": "reference"} for item in evidence],
            confidence=score,
            risk_tier=decision.risk_tier,
            rationale=decision.reason,
            idempotency_key=proposal_key,
            metadata=metadata,
            consolidated_observation_id=observation.id,
        )
        return ConsolidationResult(
            observation=observation,
            proposal=proposal,
            admission=decision,
        )

    consolidate_observations = consolidate
    consolidate_background = consolidate

    @staticmethod
    def _content(payload: Mapping[str, Any] | None, texts: Sequence[str]) -> str:
        if payload:
            for key in ("content", "text", "summary", "value"):
                value = payload.get(key)
                if value is not None and str(value).strip():
                    return str(value)
        return "\n".join(texts)

    @staticmethod
    def _extract(
        items: Sequence[Any],
    ) -> tuple[
        list[dict[str, Any]],
        list[Any],
        list[Any],
        list[str],
        list[str],
    ]:
        references: list[dict[str, Any]] = []
        evidence_ids: list[Any] = []
        supporting_ids: list[Any] = []
        fact_keys: list[str] = []
        texts: list[str] = []
        for item in items:
            if isinstance(item, EvidenceReference):
                references.append(item.to_dict())
                evidence_ids.append(item.id)
                if item.fact_key:
                    fact_keys.append(item.fact_key)
                if item.text:
                    texts.append(item.text)
                continue
            identifier = _value(
                item,
                "evidence_id",
                "memory_id",
                "observation_id",
                "source_observation_id",
                "id",
            )
            if identifier is None and isinstance(item, (str, uuid.UUID)):
                identifier = item
            if identifier is not None:
                evidence_ids.append(identifier)
                reference: dict[str, Any] = {
                    "id": str(identifier),
                    "kind": str(_value(item, "kind", default="memory")),
                }
                item_fact = _value(item, "fact_key")
                if item_fact:
                    reference["fact_key"] = str(item_fact)
                    fact_keys.append(str(item_fact))
                item_confidence = _value(item, "confidence")
                if item_confidence is not None:
                    reference["confidence"] = _confidence(item_confidence)
                item_text = _value(item, "content", "text", "observation")
                if item_text is not None and str(item_text).strip():
                    reference["text"] = str(item_text)
                    texts.append(str(item_text))
                references.append(reference)
            nested_fact = _value(item, "fact_keys")
            fact_keys.extend(_string_values(nested_fact))
            nested_evidence = _value(item, "evidence_ids")
            evidence_ids.extend(_as_sequence(nested_evidence))
            nested_support = _value(item, "supporting_ids")
            supporting_ids.extend(_as_sequence(nested_support))
            nested_source = _value(item, "source_observation_ids")
            supporting_ids.extend(_as_sequence(nested_source))
        return (
            references,
            _unique(evidence_ids),
            _unique(supporting_ids),
            _unique(fact_keys),
            _unique(texts),
        )

    async def apply(
        self,
        proposal: MemoryProposal | uuid.UUID,
        *,
        writer: CanonicalMemoryWriter | Any | None = None,
        actor_id: uuid.UUID | None = None,
        canonical_memory_id: uuid.UUID | None = None,
    ) -> ApplyResult:
        selected_writer = writer or self._writer
        if selected_writer is None:
            raise CanonicalWriterRequired(
                "A canonical memory writer must be supplied at the apply boundary."
            )
        if isinstance(proposal, uuid.UUID):
            target_proposal = await self._get_proposal(proposal)
        else:
            target_proposal = proposal
        if target_proposal is None:
            raise ConsolidationError("The proposal does not exist in the tenant.")
        proposal = target_proposal
        if proposal.validation_state not in {
            ProposalValidationState.VALIDATED.value,
            ProposalValidationState.APPROVED.value,
        }:
            raise ProposalNotReadyError(
                "Only an explicitly validated or approved proposal can be applied."
            )
        result = await self._invoke_writer(
            selected_writer,
            proposal,
            organization_id=proposal.organization_id,
            user_id=proposal.user_id,
            actor_id=actor_id,
        )
        applied_memory_id = canonical_memory_id or self._canonical_id(result)
        method = getattr(self._proposals, "mark_applied", None)
        if method is not None:
            await method(
                proposal.id,
                canonical_memory_id=applied_memory_id,
            )
        else:
            proposal.validation_state = ProposalValidationState.APPLIED.value
            proposal.applied_at = _utcnow()
            if applied_memory_id is not None:
                proposal.canonical_memory_id = applied_memory_id
            flush = getattr(getattr(self._proposals, "session", None), "flush", None)
            if flush is not None:
                await flush()
        return ApplyResult(
            proposal_id=proposal.id,
            canonical_memory_id=applied_memory_id,
            writer_result=result,
        )

    apply_proposal = apply

    @staticmethod
    async def _invoke_writer(
        writer: Any,
        proposal: MemoryProposal,
        **kwargs: Any,
    ) -> Any:
        method = getattr(writer, "apply_proposal", None) or getattr(writer, "apply", None)
        if method is None:
            raise CanonicalWriterRequired(
                "The canonical writer must expose apply_proposal or apply."
            )
        call_kwargs = dict(kwargs)
        try:
            parameters = inspect.signature(method).parameters
        except (TypeError, ValueError):
            parameters = {}
        if parameters and not any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        ):
            call_kwargs = {
                name: value for name, value in call_kwargs.items() if name in parameters
            }
        result = method(proposal, **call_kwargs)
        return await result if inspect.isawaitable(result) else result

    @staticmethod
    def _canonical_id(result: Any) -> uuid.UUID | None:
        value = None
        if isinstance(result, uuid.UUID):
            value = result
        elif isinstance(result, Mapping):
            value = result.get("canonical_memory_id") or result.get("memory_id")
        else:
            value = getattr(result, "canonical_memory_id", None) or getattr(result, "memory_id", None)
            if value is None:
                value = getattr(result, "id", None)
        if value is None:
            return None
        try:
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        except (TypeError, ValueError):
            return None


class ProposalApplyService:
    def __init__(
        self,
        proposal_repository: Any,
        writer: CanonicalMemoryWriter | Any,
    ) -> None:
        self._proposals = proposal_repository
        self._writer = writer

    async def apply(
        self,
        proposal: MemoryProposal | uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        canonical_memory_id: uuid.UUID | None = None,
    ) -> ApplyResult:
        service = CortexConsolidationService(
            proposal_repository=self._proposals,
            writer=self._writer,
        )
        return await service.apply(
            proposal,
            actor_id=actor_id,
            canonical_memory_id=canonical_memory_id,
        )


ConsolidationEngine = CortexConsolidationService
MemoryConsolidationService = CortexConsolidationService


__all__ = [
    "AdmissionDecision",
    "AdmissionPolicy",
    "ApplyResult",
    "CanonicalMemoryWriter",
    "CanonicalWriterRequired",
    "ConsolidationEngine",
    "ConsolidationError",
    "ConsolidationResult",
    "CortexConsolidationService",
    "EvidenceReference",
    "InvalidEvidenceError",
    "MemoryConsolidationService",
    "ObservationStore",
    "PolicyViolation",
    "ProposalApplyService",
    "ProposalNotReadyError",
    "ProposalStore",
    "RiskTieredAdmissionPolicy",
]
