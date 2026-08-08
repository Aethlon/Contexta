"""Extraction-to-storage pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from contexta.core.extraction.worker import ExtractionWorker
from contexta.core.schemas import ObservationPayload
from contexta.core.scoring.engine import MemoryScoringEngine


@dataclass
class PipelineResult:
    extracted_count: int
    stored_count: int
    skipped_count: int
    details: list[dict[str, Any]]


class MemoryPipeline:
    """Coordinate observation extraction through storage-adjacent steps."""

    def __init__(
        self,
        *,
        extraction_worker: ExtractionWorker | None = None,
        scoring_engine: MemoryScoringEngine | None = None,
    ) -> None:
        self._extractor = extraction_worker or ExtractionWorker()
        self._scoring = scoring_engine or MemoryScoringEngine()

    async def process_observation(self, payload: ObservationPayload) -> PipelineResult:
        extracted = await self._extractor.extract(payload)
        details: list[dict[str, Any]] = []
        for memory in extracted:
            importance = self._scoring.compute_importance(
                memory.memory_type,
                memory.content,
            )
            if importance.rejected:
                details.append({"title": memory.title, "status": "skipped_low_value"})
                continue
            details.append(
                {
                    "title": memory.title,
                    "status": "ready_for_storage",
                    "importance": importance.final_score,
                    "confidence": self._scoring.compute_confidence(memory.source_type),
                }
            )
        return PipelineResult(
            extracted_count=len(extracted),
            stored_count=sum(1 for item in details if item["status"] == "ready_for_storage"),
            skipped_count=sum(1 for item in details if item["status"] != "ready_for_storage"),
            details=details,
        )
