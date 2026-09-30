"""Regression coverage for the at-rest encryption write path.

Before v1.5.1, `encrypt_content` was called from exactly three places, all inside
`MemoryRepository`. The ingestion orchestrator builds its `MemoryRecord` rows
itself and persists them with `session.add_all`, so ~89% of a real database was
plaintext while the code and the docs advertised authenticated at-rest
encryption. `plaintext_content` tolerates both forms on read, which is why it was
never noticed.

These tests assert the *storage* property rather than the read behaviour: after
any ORM write commits, `memory_record.content` is a single `enc:v1:` envelope.
They need a real PostgreSQL with pgvector, because the guarantee under test is
about the bytes that reach the column, and a mock session proves nothing. A
throwaway database is created and dropped around the module.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from contexta.config.settings import get_settings
from contexta.core.crypto.vault import decrypt_content, encrypt_content
from contexta.models.memory import (
    ENCRYPTED_CONTENT_PREFIX,
    MemoryRecord,
    seal_content_for_storage,
)
from contexta.repositories.memory_repo import MemoryRepository

_PLAINTEXT = "The user moved from New York to London and prefers Postgres over Mongo."

# `memory_record.valid_from` / `created_at` / `updated_at` are naive
# `timestamp without time zone` columns, so these are deliberately naive.
_NAIVE_NOW = datetime(2026, 9, 30, 12, 0, 0)  # noqa: DTZ001


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _url_for_database(database_url: str, database: str) -> str:
    base, _, _ = database_url.rpartition("/")
    return f"{base}/{database}"


async def _create_database(admin_url: str, name: str) -> None:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        await engine.dispose()


async def _drop_database(admin_url: str, name: str) -> None:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        await engine.dispose()


async def _prepare_schema(database_url: str) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            # Only the table under test. `Base.metadata.create_all()` is wrong
            # here: revision 020 dropped tables whose ORM models still exist.
            await connection.run_sync(MemoryRecord.__table__.create)
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def scratch_database_url() -> Iterator[str]:
    """A disposable database holding one real `memory_record` table."""
    configured = get_settings().database_url
    admin_url = _url_for_database(configured, "postgres")
    name = f"contexta_encryption_{uuid.uuid4().hex[:12]}"

    try:
        _run(_create_database(admin_url, name))
    except Exception as exc:  # noqa: BLE001 - the suite must run without a database
        pytest.skip(f"no PostgreSQL available for the encryption write-path tests: {exc}")

    database_url = _url_for_database(configured, name)
    try:
        _run(_prepare_schema(database_url))
    except Exception as exc:  # noqa: BLE001
        _run(_drop_database(admin_url, name))
        pytest.skip(f"could not build the scratch memory_record schema: {exc}")

    try:
        yield database_url
    finally:
        _run(_drop_database(admin_url, name))


@pytest.fixture
async def session(scratch_database_url: str) -> AsyncIterator[Any]:
    """A session with `expire_on_commit=False`, as `contexta.db` builds it."""
    engine = create_async_engine(scratch_database_url, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as open_session:
        yield open_session
    await engine.dispose()


def _record(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    content: str,
    **overrides: Any,
) -> MemoryRecord:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "organization_id": organization_id,
        "memory_type": "fact",
        "title": "Where the user lives",
        "content": content,
        "source_type": "user_explicit",
        "confidence": 1.0,
        "importance": 0.5,
        "utility_score": 0.0,
        "memory_state": "active",
        "is_pinned": False,
        "is_archived": False,
        "valid_from": _NAIVE_NOW,
    }
    values.update(overrides)
    return MemoryRecord(**values)


async def _stored_content(session: Any, record_id: uuid.UUID) -> str | None:
    """Read the raw column, bypassing every hydration helper."""
    result = await session.execute(
        select(MemoryRecord.content).where(MemoryRecord.id == record_id)
    )
    return result.scalar_one()


async def _count_rows_whose_content_is_plaintext(session: Any) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(MemoryRecord)
        .where(MemoryRecord.content.not_like(f"{ENCRYPTED_CONTENT_PREFIX}%"))
    )
    return int(result.scalar_one())


async def test_orchestrator_style_add_all_seals_content(scratch_database_url, session) -> None:
    """`session.add_all` of a plaintext record — the path that leaked 89%."""
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    record = _record(organization_id, user_id, _PLAINTEXT)

    session.add_all([record])
    await session.commit()

    stored = await _stored_content(session, record.id)
    assert stored is not None
    assert stored.startswith(ENCRYPTED_CONTENT_PREFIX), "cleartext reached memory_record.content"
    assert _PLAINTEXT not in stored
    assert decrypt_content(stored, str(organization_id)) == _PLAINTEXT


async def test_several_records_sealed_in_one_flush(scratch_database_url, session) -> None:
    """A batch insert is one flush; every row in it must come out sealed."""
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    records = [
        _record(organization_id, user_id, f"{_PLAINTEXT} Fact number {index}.")
        for index in range(5)
    ]

    session.add_all(records)
    await session.commit()

    assert await _count_rows_whose_content_is_plaintext(session) == 0


async def test_repository_create_seals_exactly_once(scratch_database_url, session) -> None:
    """`create()` seals, then the flush hook must not seal the sealed value again."""
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    repository = MemoryRepository(session, tenant_id=organization_id)
    record = _record(organization_id, user_id, _PLAINTEXT)

    created = await repository.create(record)
    await session.commit()

    stored = await _stored_content(session, created.id)
    assert stored is not None
    # Exactly one envelope: a nested seal would decrypt to the inner `enc:v1:...`
    # token instead of the original sentence.
    assert stored.startswith(ENCRYPTED_CONTENT_PREFIX)
    assert stored.count(ENCRYPTED_CONTENT_PREFIX) == 1
    assert decrypt_content(stored, str(organization_id)) == _PLAINTEXT
    # The repository hydrates the row it returns, so callers still see plaintext.
    assert created.plaintext_content == _PLAINTEXT


async def test_already_sealed_content_is_left_untouched(scratch_database_url, session) -> None:
    """Idempotency: a sealed value must survive a write byte for byte."""
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    sealed = encrypt_content(_PLAINTEXT, str(organization_id))
    assert sealed is not None
    record = _record(organization_id, user_id, sealed)

    session.add_all([record])
    await session.commit()

    assert await _stored_content(session, record.id) == sealed


async def test_plaintext_content_round_trips_fresh_and_legacy(scratch_database_url, session) -> None:
    """Readers tolerate both forms: a newly sealed row and a pre-fix plaintext row."""
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()

    fresh = _record(organization_id, user_id, _PLAINTEXT)
    legacy = _record(organization_id, user_id, _PLAINTEXT)

    session.add_all([fresh])
    await session.commit()

    # A Core insert is what a row written before the fix looks like: the column
    # holds the sentence itself. It must still read back intact.
    await session.execute(
        insert(MemoryRecord).values(
            id=legacy.id,
            user_id=user_id,
            organization_id=organization_id,
            memory_type="fact",
            title="Where the user lives",
            content=_PLAINTEXT,
            source_type="user_explicit",
            confidence=1.0,
            importance=0.5,
            utility_score=0.0,
            memory_state="active",
            is_pinned=False,
            is_archived=False,
            valid_from=_NAIVE_NOW,
            created_at=_NAIVE_NOW,
            updated_at=_NAIVE_NOW,
        )
    )
    await session.commit()

    rows = (
        await session.execute(
            select(MemoryRecord).where(MemoryRecord.id.in_([fresh.id, legacy.id]))
        )
    ).scalars().all()
    assert len(rows) == 2
    assert {row.plaintext_content for row in rows} == {_PLAINTEXT}

    stored = await _stored_content(session, legacy.id)
    assert stored == _PLAINTEXT, "reading a legacy row must not rewrite it"


async def test_null_content_stays_null() -> None:
    """`content IS NULL` is never handed to the vault."""
    record = _record(uuid.uuid4(), uuid.uuid4(), _PLAINTEXT)
    record.content = None  # type: ignore[assignment]

    seal_content_for_storage(record)

    assert record.content is None
    assert encrypt_content(None, str(record.organization_id)) is None


async def test_in_session_content_change_is_sealed(scratch_database_url, session) -> None:
    """A content change on a persisted row goes out sealed too."""
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    record = _record(organization_id, user_id, _PLAINTEXT)
    session.add_all([record])
    await session.commit()

    repository = MemoryRepository(session, tenant_id=organization_id)
    loaded = await repository.get_by_id(record.id)
    assert loaded is not None
    assert loaded.plaintext_content == _PLAINTEXT

    loaded.content = "The user moved from New York to Lisbon and prefers Postgres over Mongo."
    session.add(loaded)
    await session.commit()

    stored = await _stored_content(session, record.id)
    assert stored is not None
    assert stored.startswith(ENCRYPTED_CONTENT_PREFIX)
    assert decrypt_content(stored, str(organization_id)) == loaded.plaintext_content
    assert "Lisbon" in loaded.plaintext_content


async def test_unrelated_update_does_not_reseal_content(scratch_database_url, session) -> None:
    """A hydrated row keeps plaintext in memory; flushing it must not double-seal."""
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    record = _record(organization_id, user_id, _PLAINTEXT)
    session.add_all([record])
    await session.commit()
    sealed_after_insert = await _stored_content(session, record.id)

    repository = MemoryRepository(session, tenant_id=organization_id)
    loaded = await repository.get_by_id(record.id)
    assert loaded is not None
    assert loaded.content == _PLAINTEXT

    loaded.importance = 0.9
    session.add(loaded)
    await session.commit()

    # The nonce is random, so a re-seal would change the stored bytes.
    assert await _stored_content(session, record.id) == sealed_after_insert


async def test_derived_key_is_tenant_scoped(scratch_database_url, session) -> None:
    """Same plaintext, two organizations, two unrelated ciphertexts."""
    first_org = uuid.uuid4()
    second_org = uuid.uuid4()
    user_id = uuid.uuid4()
    first = _record(first_org, user_id, _PLAINTEXT)
    second = _record(second_org, user_id, _PLAINTEXT)

    session.add_all([first, second])
    await session.commit()

    first_stored = await _stored_content(session, first.id)
    second_stored = await _stored_content(session, second.id)
    assert first_stored != second_stored
    assert decrypt_content(first_stored, str(first_org)) == _PLAINTEXT
    assert decrypt_content(second_stored, str(second_org)) == _PLAINTEXT
    # Neither opens under the other's key.
    assert decrypt_content(first_stored, str(second_org)) != _PLAINTEXT


async def test_repository_update_by_id_seals_the_core_statement(scratch_database_url, session) -> None:
    """`update_by_id` issues Core DML, which no mapper event can see.

    It is therefore the one production content write that has to seal its own
    value, and this pins that it does. A raw
    `update(MemoryRecord).values(content=...)` from new code would bypass the
    model hooks entirely — that is the residual gap, not a supported path.
    """
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    record = _record(organization_id, user_id, _PLAINTEXT)
    session.add_all([record])
    await session.commit()

    repository = MemoryRepository(session, tenant_id=organization_id)
    rows = await repository.update_by_id(record.id, {"content": "The user moved to Lisbon."})
    await session.commit()

    assert rows == 1
    stored = await _stored_content(session, record.id)
    assert stored is not None
    assert stored.startswith(ENCRYPTED_CONTENT_PREFIX)
    assert decrypt_content(stored, str(organization_id)) == "The user moved to Lisbon."