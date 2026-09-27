from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import AliasChoices, Field

from contexta.contracts.runtime import (
    CANONICAL_WRITE_AUTHORITY,
    CanonicalWriteAuthority,
    ContractModel,
    EvidenceRef,
    Scope,
    ScopedRequest,
    json_dumps,
    load_model,
)


class ContextFormat(str, Enum):
    MARKDOWN = "markdown"
    PLAIN = "plain"
    XML = "xml"
    JSON = "json"


class ContextBlockKind(str, Enum):
    IDENTITY = "identity"
    PREFERENCE = "preference"
    RULE = "rule"
    PROJECT = "project"
    GOAL = "goal"
    EVENT = "event"
    FACT = "fact"
    CONVERSATION = "conversation"
    GRAPH = "graph"
    CUSTOM = "custom"


class ContextMessage(ContractModel):
    role: str = "user"
    content: str = Field(min_length=1)
    message_id: str | None = Field(default=None, min_length=1)
    created_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BuildContextRequest(ScopedRequest):
    focus: str | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("focus", "query", "query_text"),
    )
    messages: list[ContextMessage] = Field(default_factory=list)
    token_budget: int | None = Field(default=None, ge=1)
    max_memories: int = Field(default=20, ge=1, le=100)
    graph_depth: int = Field(default=2, ge=0, le=5)
    include_user_model: bool = True
    include_recent_messages: bool = True
    include_evidence: bool = True
    format: ContextFormat = ContextFormat.MARKDOWN

    @property
    def query(self) -> str | None:
        return self.focus

    @property
    def output_format(self) -> ContextFormat:
        return self.format


class ContextBlock(ContractModel):
    block_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("block_id", "id"),
    )
    kind: ContextBlockKind = ContextBlockKind.CUSTOM
    content: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    version: int = Field(default=0, ge=0)
    token_count: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.block_id

    @property
    def source_refs(self) -> list[EvidenceRef]:
        return self.evidence


class ContextPackage(ContractModel):
    package_id: str = Field(
        default_factory=lambda: uuid4().hex,
        min_length=1,
        validation_alias=AliasChoices("package_id", "context_package_id"),
    )
    schema_version: Literal["1.0"] = "1.0"
    scope: Scope
    operation_id: str | None = Field(default=None, min_length=1)
    write_authority: CanonicalWriteAuthority = CANONICAL_WRITE_AUTHORITY
    blocks: list[ContextBlock] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    text: str | None = None
    token_budget: int | None = Field(default=None, ge=1)
    token_count: int = Field(default=0, ge=0)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def context_package_id(self) -> str:
        return self.package_id

    @property
    def version(self) -> str:
        return self.schema_version

    @property
    def canonical_write_authority(self) -> str:
        return self.write_authority

    @property
    def all_evidence(self) -> list[EvidenceRef]:
        references: list[EvidenceRef] = []
        seen: set[str] = set()
        for reference in [*self.evidence, *(item for block in self.blocks for item in block.evidence)]:
            if reference.id not in seen:
                seen.add(reference.id)
                references.append(reference)
        return references

    def serialize(self, *, by_alias: bool = True) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=by_alias)

    def to_dict(self, *, by_alias: bool = True) -> dict[str, Any]:
        return self.serialize(by_alias=by_alias)

    def to_json(self, *, indent: int | None = None) -> str:
        return json_dumps(self.serialize(), indent=indent)

    def as_dict(self, *, by_alias: bool = True) -> dict[str, Any]:
        return self.serialize(by_alias=by_alias)

    def as_json(self, *, indent: int | None = None) -> str:
        return self.to_json(indent=indent)

    def to_prompt(self, output_format: ContextFormat | str = ContextFormat.MARKDOWN) -> str:
        if self.text is not None:
            return self.text
        selected_format = ContextFormat(output_format)
        if selected_format == ContextFormat.JSON:
            return json.dumps(self.serialize(), ensure_ascii=False, indent=2)
        if selected_format == ContextFormat.XML:
            lines = ["<context_package>"]
            for block in self.blocks:
                lines.append(
                    f'  <block id="{block.block_id}" kind="{block.kind.value}">{block.content}</block>'
                )
            lines.append("</context_package>")
            return "\n".join(lines)
        if selected_format == ContextFormat.PLAIN:
            return "\n".join(block.content for block in self.blocks)
        return "\n\n".join(
            f"## {block.kind.value.title()}\n{block.content}" for block in self.blocks
        )

    def render(self, output_format: ContextFormat | str = ContextFormat.MARKDOWN) -> str:
        return self.to_prompt(output_format)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ContextPackage:
        data = dict(payload)
        nested = data.get("context_package")
        if isinstance(nested, Mapping):
            data = dict(nested)
        return cls.model_validate(data)

    @classmethod
    def from_json(cls, payload: str | bytes) -> ContextPackage:
        data = json.loads(payload)
        if not isinstance(data, Mapping):
            raise TypeError("context package JSON must contain an object")
        return cls.from_dict(data)

    @classmethod
    def deserialize(cls, payload: Mapping[str, Any] | str | bytes) -> ContextPackage:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        if isinstance(payload, str):
            return cls.from_json(payload)
        return cls.from_dict(payload)


ContextPackageRequest = BuildContextRequest
ContextPackageEnvelope = ContextPackage


def serialize_context_package(package: ContextPackage) -> dict[str, Any]:
    return package.serialize()


def deserialize_context_package(payload: Mapping[str, Any] | str | bytes) -> ContextPackage:
    return ContextPackage.deserialize(payload)


def load_context_package(model_type: type[ContractModel], payload: Mapping[str, Any] | str) -> ContractModel:
    return load_model(model_type, payload)
