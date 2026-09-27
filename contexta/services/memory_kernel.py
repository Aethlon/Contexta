from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from contexta.contracts.context import BuildContextRequest, ContextPackage
from contexta.contracts.runtime import (
    CANONICAL_WRITE_AUTHORITY,
    BlockUpdateProposal,
    CorrectionResult,
    CorrectRequest,
    ExplainRequest,
    ExplanationResult,
    GetOperationRequest,
    GraphSearchResult,
    ObserveRequest,
    ObserveResult,
    OperationResult,
    ProposeBlockUpdateRequest,
    RecallRequest,
    RecallResult,
    SearchGraphRequest,
)


@runtime_checkable
class MemoryKernel(Protocol):
    @property
    def canonical_write_authority(self) -> Literal["contexta"]:
        ...

    async def observe(self, request: ObserveRequest) -> ObserveResult:
        ...

    async def recall(self, request: RecallRequest) -> RecallResult:
        ...

    async def build_context(self, request: BuildContextRequest) -> ContextPackage:
        ...

    async def explain(self, request: ExplainRequest) -> ExplanationResult:
        ...

    async def correct(self, request: CorrectRequest) -> CorrectionResult:
        ...

    async def propose_block_update(
        self,
        request: ProposeBlockUpdateRequest,
    ) -> BlockUpdateProposal:
        ...

    async def search_graph(self, request: SearchGraphRequest) -> GraphSearchResult:
        ...

    async def get_operation(self, request: GetOperationRequest) -> OperationResult | None:
        ...


MemoryReadKernel = MemoryKernel
MemoryWriteKernel = MemoryKernel
CONTEXTA_WRITE_AUTHORITY = CANONICAL_WRITE_AUTHORITY
