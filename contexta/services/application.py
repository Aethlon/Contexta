from __future__ import annotations

from typing import Protocol, runtime_checkable

from contexta.services.context_package import ContextPackageService
from contexta.services.memory_kernel import MemoryKernel


@runtime_checkable
class MemoryApplicationService(MemoryKernel, ContextPackageService, Protocol):
    pass


ContextaApplicationService = MemoryApplicationService
ContextApplicationService = MemoryApplicationService
ApplicationService = MemoryApplicationService
MemoryRuntime = MemoryApplicationService
