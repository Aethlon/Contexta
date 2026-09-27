from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from contexta.core.pipeline import FastMemoryOrchestrator
from contexta.core.schemas import ObservationPayload
from contexta.services.artifacts import SUCCESSFUL_EXTRACTION_STATUSES


@dataclass(frozen=True, slots=True)
class ArtifactIngestionResult:
    chunk_count: int
    memory_ids: list[str]
    extracted_count: int


class ArtifactMemoryIngestor:
    def __init__(
        self,
        orchestrator: FastMemoryOrchestrator | None = None,
        *,
        chunk_size: int = 12000,
    ) -> None:
        self._orchestrator = orchestrator or FastMemoryOrchestrator()
        self._chunk_size = max(1000, int(chunk_size))

    async def ingest(
        self,
        artifact: Any,
        session: AsyncSession,
    ) -> ArtifactIngestionResult:
        text = str(getattr(artifact, "extracted_text", "") or "").strip()
        status = str(getattr(artifact, "extraction_status", "")).strip().casefold()
        if not text or status not in SUCCESSFUL_EXTRACTION_STATUSES:
            return ArtifactIngestionResult(0, [], 0)

        chunks = self._chunks(text)
        memory_ids: list[str] = []
        extracted_count = 0
        created_at = self._as_datetime(getattr(artifact, "created_at", None))
        organization_id = UUID(str(artifact.organization_id))
        user_id = UUID(str(artifact.user_id))
        artifact_id = str(artifact.id)
        for index, chunk in enumerate(chunks):
            payload = ObservationPayload(
                user_id=user_id,
                organization_id=organization_id,
                session_id=uuid4(),
                messages=[
                    {
                        "role": "user",
                        "content": chunk,
                        "text": chunk,
                        "message_id": f"artifact:{artifact_id}:{index}",
                        "occurred_at": created_at.isoformat() if created_at else None,
                        "observed_at": created_at.isoformat() if created_at else None,
                    }
                ],
                occurred_at=created_at,
                observed_at=created_at,
                source_id=f"artifact:{artifact_id}",
                timezone="UTC",
                metadata={
                    "artifact_id": artifact_id,
                    "filename": getattr(artifact, "filename", None),
                    "mime_type": getattr(artifact, "mime_type", None),
                    "chunk_index": index,
                    "chunk_count": len(chunks),
                },
            )
            result = await self._orchestrator.orchestrate(payload, session)
            extracted_count += result.extracted_count
            memory_ids.extend(result.embedding_memory_ids)
        return ArtifactIngestionResult(len(chunks), list(dict.fromkeys(memory_ids)), extracted_count)

    def _chunks(self, text: str) -> list[str]:
        if len(text) <= self._chunk_size:
            return [text]
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + self._chunk_size)
            if end < len(text):
                boundary = text.rfind("\n\n", start + self._chunk_size // 2, end)
                if boundary > start:
                    end = boundary
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(text):
                break
            start = end
        return chunks

    @staticmethod
    def _as_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = ["ArtifactIngestionResult", "ArtifactMemoryIngestor"]
