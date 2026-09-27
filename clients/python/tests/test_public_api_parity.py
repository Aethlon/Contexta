"""Parity guard for the Python and TypeScript Contexta SDKs.

Both clients are asserted against the single source of truth in
``clients/public-api.manifest.json``. Python is checked by reflection; the
TypeScript client is checked by parsing ``clients/typescript/src/client.ts`` so
this test runs without a Node toolchain. The mirror-image runtime check lives in
``clients/typescript/tests/parity.test.ts``.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from typing import Any

import pytest

from contexta_client.async_client import AsyncContexta
from contexta_client.client import Contexta

CLIENTS_DIR = Path(__file__).resolve().parents[2]
MANIFEST_PATH = CLIENTS_DIR / "public-api.manifest.json"
TS_CLIENT_PATH = CLIENTS_DIR / "typescript" / "src" / "client.ts"

CLASS_MEMBER = re.compile(r"^\s{2}(?:public\s+|private\s+|protected\s+)?"
                          r"(?:static\s+)?(?:async\s+)?(?P<name>[A-Za-z_$][\w$]*)\s*[(<]")
IGNORED_TS_MEMBERS = {"constructor"}
TS_CLASS_HEAD = re.compile(r"^export\s+class\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?:extends\s+(?P<base>[A-Za-z_$][\w$]*))?")


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.is_file():
        pytest.fail(f"Canonical API manifest is missing: {MANIFEST_PATH}")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _python_api(cls: type) -> set[str]:
    return {
        name
        for name, _ in inspect.getmembers(cls, predicate=callable)
        if not name.startswith("_")
    }


def _ts_class_bodies(source: str) -> dict[str, str]:
    lines = source.splitlines()
    bodies: dict[str, list[str]] = {}
    bases: dict[str, str | None] = {}
    current: str | None = None
    for line in lines:
        header = TS_CLASS_HEAD.match(line)
        if header:
            current = header.group("name")
            bodies[current] = []
            bases[current] = header.group("base")
            continue
        if current is None:
            continue
        if line and not line[0].isspace():
            current = None
            continue
        bodies[current].append(line)
    return {name: "\n".join(body) for name, body in bodies.items()}, bases


def _ts_api(source: str, class_name: str) -> set[str]:
    bodies, bases = _ts_class_bodies(source)
    if class_name not in bodies:
        pytest.fail(f"Class {class_name} not found in {TS_CLIENT_PATH}")
    names: set[str] = set()
    seen: set[str] = set()
    current: str | None = class_name
    while current and current not in seen:
        seen.add(current)
        if current not in bodies:
            pytest.fail(f"Class {current} not found in {TS_CLIENT_PATH}")
        names.update(
            match.group("name")
            for match in (CLASS_MEMBER.match(line) for line in bodies[current].splitlines())
            if match and match.group("name") not in IGNORED_TS_MEMBERS
        )
        current = bases.get(current)
    return names


def test_manifest_has_unique_method_names(manifest: dict[str, Any]) -> None:
    entries = manifest["methods"]
    python_names = [entry["name"] for entry in entries]
    ts_names = [entry["typescript"] for entry in entries]
    assert len(set(python_names)) == len(python_names)
    assert len(set(ts_names)) == len(ts_names)
    assert all(entry["name"] and entry["typescript"] for entry in entries)


@pytest.mark.parametrize("cls", [Contexta, AsyncContexta])
def test_python_client_matches_manifest(manifest: dict[str, Any], cls: type) -> None:
    expected = {entry["name"] for entry in manifest["methods"]}
    assert _python_api(cls) == expected, (
        f"{cls.__name__} drifted from {MANIFEST_PATH.name}: "
        f"missing={sorted(expected - _python_api(cls))} "
        f"extra={sorted(_python_api(cls) - expected)}"
    )


@pytest.mark.parametrize(
    "class_key",
    ["clientClass", "asyncClientClass"],
)
def test_typescript_client_matches_manifest(manifest: dict[str, Any], class_key: str) -> None:
    if not TS_CLIENT_PATH.is_file():
        pytest.fail(f"TypeScript client is missing: {TS_CLIENT_PATH}")
    source = TS_CLIENT_PATH.read_text(encoding="utf-8")
    class_name = manifest["typescript"][class_key]
    expected = {entry["typescript"] for entry in manifest["methods"]}
    actual = _ts_api(source, class_name)
    assert actual == expected, (
        f"{class_name} drifted from {MANIFEST_PATH.name}: "
        f"missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
    )


def test_deprecated_aliases_resolve(manifest: dict[str, Any]) -> None:
    aliases = manifest["python"]["deprecatedAliases"]
    assert aliases == {"contexta": "Contexta", "Asynccontexta": "AsyncContexta"}
    from contexta_client import async_client as async_module
    from contexta_client import client as sync_module

    with pytest.warns(DeprecationWarning):
        assert sync_module.contexta is Contexta
    with pytest.warns(DeprecationWarning):
        assert async_module.Asynccontexta is AsyncContexta
