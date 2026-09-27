from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from contexta.contracts.context import (
    BuildContextRequest,
    ContextPackage,
    deserialize_context_package,
    serialize_context_package,
)


@runtime_checkable
class ContextPackageService(Protocol):
    async def build_context(self, request: BuildContextRequest) -> ContextPackage:
        ...

    def serialize_context_package(self, package: ContextPackage) -> dict[str, Any]:
        ...

    def deserialize_context_package(
        self,
        payload: Mapping[str, Any] | str | bytes,
    ) -> ContextPackage:
        ...


class ContextPackageSerializer:
    @staticmethod
    def serialize(package: ContextPackage) -> dict[str, Any]:
        return serialize_context_package(package)

    @staticmethod
    def deserialize(payload: Mapping[str, Any] | str | bytes) -> ContextPackage:
        return deserialize_context_package(payload)

    @staticmethod
    def to_json(package: ContextPackage, *, indent: int | None = None) -> str:
        return package.to_json(indent=indent)

    @staticmethod
    def from_json(payload: str | bytes) -> ContextPackage:
        return ContextPackage.from_json(payload)


ContextPackageBuilder = ContextPackageService
ContextSerializer = ContextPackageSerializer
