from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "ApplicationService": ("contexta.services.application", "ApplicationService"),
    "ContextaApplicationService": (
        "contexta.services.application",
        "ContextaApplicationService",
    ),
    "ContextApplicationService": (
        "contexta.services.application",
        "ContextApplicationService",
    ),
    "MemoryApplicationService": (
        "contexta.services.application",
        "MemoryApplicationService",
    ),
    "MemoryRuntime": ("contexta.services.application", "MemoryRuntime"),
    "ContextPackageBuilder": (
        "contexta.services.context_package",
        "ContextPackageBuilder",
    ),
    "ContextPackageSerializer": (
        "contexta.services.context_package",
        "ContextPackageSerializer",
    ),
    "ContextPackageService": (
        "contexta.services.context_package",
        "ContextPackageService",
    ),
    "ContextSerializer": ("contexta.services.context_package", "ContextSerializer"),
    "ContextaKernel": ("contexta.services.kernel", "ContextaKernel"),
    "ContextaMemoryKernel": ("contexta.services.kernel", "ContextaMemoryKernel"),
    "Kernel": ("contexta.services.kernel", "Kernel"),
    "MemoryKernelAdapter": ("contexta.services.kernel", "MemoryKernelAdapter"),
    "MemoryKernelService": ("contexta.services.kernel", "MemoryKernelService"),
    "CONTEXTA_WRITE_AUTHORITY": (
        "contexta.services.memory_kernel",
        "CONTEXTA_WRITE_AUTHORITY",
    ),
    "MemoryKernel": ("contexta.services.memory_kernel", "MemoryKernel"),
    "MemoryReadKernel": ("contexta.services.memory_kernel", "MemoryReadKernel"),
    "MemoryWriteKernel": ("contexta.services.memory_kernel", "MemoryWriteKernel"),
}

__all__ = tuple(sorted(_EXPORTS))


def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
