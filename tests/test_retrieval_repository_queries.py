"""Repository-level contracts for the three retrieval channels' SQL.

The subjects here are the *statements* the repositories build, so the assertions
render the SQL and, where a predicate is the whole point of the test, apply it
to fixture rows. A mock that returns whatever the test hands it would pass even
if `valid_to IS NULL` were deleted from the query, which is exactly the class of
regression these tests exist to prevent:

* the lexical channel degenerated into "the whole corpus, newest first" because
  its private stopword list did not know that `user` is a constant in every
  stored title;
* `get_linked_to_entities` published superseded facts as current;
* the graph channel had to hydrate whole memory rows just to count links.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from contexta.config.settings import OFFLINE_EMBEDDING_PROFILE
from contexta.core.lexicon import (
    DISCOURSE_STOPWORDS,
    LEXICAL_STOPWORDS,
    SESSION_AND_TEMPORAL_STOPWORDS,
    informative_terms,
)
from contexta.models.entity import MemoryEntityLink
from contexta.models.memory import MemoryRecord
from contexta.repositories.entity_repo import MemoryEntityLinkRepository
from contexta.repositories.memory_repo import LexicalSearchResult, MemoryRepository

# ─── Fixtures ─────────────────────────────────────────────────────────

_TENANT = uuid.UUID("11111111-1111-4111-8111-111111111111")
_OTHER_TENANT = uuid.UUID("22222222-2222-4222-8222-222222222222")
_USER = uuid.UUID("33333333-3333-4333-8333-333333333333")
_ENTITY = uuid.UUID("44444444-4444-4444-8444-444444444444")
_OTHER_ENTITY = uuid.UUID("55555555-5555-4555-8555-555555555555")
_UUID_TEXT = r"'[0-9a-fA-F-]{36}'"


def make_record(
    *,
    organization_id: uuid.UUID = _TENANT,
    user_id: uuid.UUID = _USER,
    valid_to: datetime | None = None,
    entity_ids: frozenset[uuid.UUID] = frozenset(),
    title: str = "the user moved Bengaluru",
    content: str = "plaintext",
) -> MemoryRecord:
    record = MemoryRecord(
        id=uuid.uuid4(),
        user_id=user_id,
        organization_id=organization_id,
        memory_type="fact",
        title=title,
        content=content,
        source_type="user_explicit",
        confidence=1.0,
        importance=0.5,
        utility_score=0.0,
        memory_state="active",
        is_archived=False,
        valid_from=datetime.now(UTC),
        valid_to=valid_to,
        created_at=datetime.now(UTC),
    )
    # Only read by RecordingSession's entity_id IN (...) emulation. An undeclared
    # attribute on a mapped instance is a plain instance attribute, never a column.
    record.entity_ids = entity_ids
    return record


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    # A UUID bind compiles to `<value>::UUID`, not to a quoted literal: the value
    # travels to Postgres out of band and the cast is what types it. Inlined
    # unquoted, `memory_record.organization_id = 1111...::UUID` parses as an
    # expression, so the emulation below never matches it and the tenant filter
    # looks absent from the query when it is in fact present. Quoting it is the
    # faithful rendering of the parameter the driver actually sends.
    if isinstance(value, (str, uuid.UUID)):
        return f"'{value}'"
    if isinstance(value, (list, tuple)):
        return ", ".join(_literal(item) for item in value)
    return str(value)


def render(statement: Any) -> str:
    """Render a statement with its binds inlined, the way Postgres receives it.

    `literal_binds` cannot be used: `websearch_to_tsquery` takes a REGCONFIG that
    SQLAlchemy refuses to inline. Substituting the compiled params by hand gives
    the same text without asking the compiler for a renderer it does not have.
    `render_postcompile` expands `IN (...)` into one bind per element, which the
    tenant/entity emulation below needs to read.
    """
    compiled = statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"render_postcompile": True},
    )
    sql = str(compiled)
    for name, value in compiled.params.items():
        sql = re.sub(
            rf"%?\({re.escape(name)}\)s|:{re.escape(name)}\b",
            _escape(_literal(value)),
            sql,
        )
    return sql


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\")


def _all_matches(pattern: str, sql: str) -> list[str]:
    return re.findall(pattern, sql)


class FakeResult:
    """The slice of SQLAlchemy's `Result` surface the repositories actually use."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = list(rows)

    def scalars(self) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: list(self._rows))

    def all(self) -> list[Any]:
        return list(self._rows)

    def one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class RecordingSession:
    """Applies the clauses these tests care about to the fixture rows.

    Tenant, `user_id`, `valid_to IS NULL` and the entity `IN (...)` list are
    honoured, so a statement that drops one of them returns rows it should not
    and the test fails on the rows rather than on the SQL text. `project` maps
    the surviving rows into the shape a two-column statement expects. `results`
    replaces the emulation entirely, for the paths that issue more than one
    statement or need a row shape the fixtures do not have.

    `results` is one entry per `execute()` call, and each entry is the *rows* of
    that result set -- so a multi-column statement fed to `one_or_none()` needs
    `[[a, b, c]]`, not `[a, b, c]`. The nesting is not decoration: passing the
    bare columns yields a scalar from `one_or_none()` and the repository under
    test is reported as broken for a fault that is only in the fixture.
    """

    def __init__(
        self,
        rows: Sequence[Any] | None = None,
        results: list[Any] | None = None,
        project: Callable[[list[Any]], list[Any]] | None = None,
    ) -> None:
        self.rows = list(rows or [])
        self.results = list(results) if results is not None else None
        self.project = project
        self.statements: list[Any] = []
        self.sql: list[str] = []

    async def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        sql = render(statement)
        self.sql.append(sql)
        if self.results is not None:
            return FakeResult(self.results.pop(0))
        rows = self._apply(sql)
        if self.project is not None:
            rows = self.project(rows)
        return FakeResult(rows)

    def _apply(self, sql: str) -> list[Any]:
        rows = list(self.rows)
        # Every tenant and user predicate in the statement, not just the first.
        # A join scopes both sides (`memory_record.organization_id = ... AND
        # memory_entity_link.organization_id = ...`), and honouring only one of
        # them would let a cross-tenant row through a test that believes the
        # query is scoped -- the failure mode where the test passes and the leak
        # is still there.
        for tenant in _all_matches(rf"organization_id = ({_UUID_TEXT})", sql):
            rows = [row for row in rows if str(row.organization_id) == tenant.strip("'")]
        for user in _all_matches(rf"\.user_id = ({_UUID_TEXT})", sql):
            rows = [row for row in rows if str(row.user_id) == user.strip("'")]
        if "valid_to IS NULL" in sql:
            rows = [row for row in rows if row.valid_to is None]
        entity_ids = re.findall(r"entity_id IN \(([^)]*)\)", sql)
        if entity_ids:
            wanted = set(re.findall(r"[0-9a-fA-F-]{36}", entity_ids[0]))
            rows = [row for row in rows if {str(e) for e in row.entity_ids} & wanted]
        return rows


def make_link(
    *,
    organization_id: uuid.UUID = _TENANT,
    entity_id: uuid.UUID = _ENTITY,
    memory_id: uuid.UUID | None = None,
) -> MemoryEntityLink:
    return MemoryEntityLink(
        memory_id=memory_id or uuid.uuid4(),
        entity_id=entity_id,
        organization_id=organization_id,
        created_at=datetime.now(UTC),
    )


def as_link_pairs(rows: list[Any]) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Project fixture memories into the `(entity_id, memory_id)` pairs SQL returns."""
    return [(entity_id, row.id) for row in rows for entity_id in sorted(row.entity_ids)]


# ─── Task 1: the shared stopword lexicon ──────────────────────────────


def test_session_and_temporal_words_are_in_both_shared_sets() -> None:
    """The 19 words an earlier refactor dropped must not get pruned again.

    `_keyword_score` in the engine downweights them to 0.25 rather than dropping
    them, so they are load-bearing for temporal and session queries; the SQL
    channel drops them from the tsquery entirely and needs the same vocabulary.
    """
    assert len(SESSION_AND_TEMPORAL_STOPWORDS) == 19
    for word in sorted(SESSION_AND_TEMPORAL_STOPWORDS):
        assert word in DISCOURSE_STOPWORDS, word
        assert word in LEXICAL_STOPWORDS, word


def test_user_is_a_stopword_on_both_paths() -> None:
    """`the user <predicate> <object>` puts `user` in every row's index."""
    assert "user" in LEXICAL_STOPWORDS
    assert "user" in DISCOURSE_STOPWORDS
    assert informative_terms(["the", "user"]) == []


def test_the_repository_keeps_no_private_stopword_copy() -> None:
    """One vocabulary, or the two paths drift apart again.

    `MemoryRepository._LEXICAL_STOPWORDS` was the duplicate that caused all of
    this: it was missing `user` while the engine's copy knew about it. Deleting
    the attribute is the only fix that cannot rot, so its absence is asserted
    rather than its contents.
    """
    private = [name for name in dir(MemoryRepository) if name.endswith("STOPWORDS")]
    assert private == []


def test_lexical_tsquery_drops_the_user_constant() -> None:
    assert MemoryRepository._lexical_tsquery_text("the user budget") == "budget"
    assert MemoryRepository._lexical_tsquery_text("What is the user's DATABASE_URL?") == (
        "database OR url"
    )
    assert MemoryRepository._lexical_tsquery_text("budget budget") == "budget"


@pytest.mark.parametrize(
    "query",
    [
        "the user",
        "user",
        "the user session yesterday",
        "the assistant system session turn conversation chat clock",
        "what about time date day month week year hour minute",
        "   ",
    ],
)
def test_stopword_only_query_builds_no_tsquery(query: str) -> None:
    assert MemoryRepository._lexical_tsquery_text(query) is None


async def test_stopword_only_query_yields_no_lexical_candidates() -> None:
    """A query of pure noise has no honest lexical answer.

    It must not degrade into matching the entire corpus: the previous
    stopword-only outcome was a full-table tsquery match ordered by
    `created_at DESC`, which the graph channel then seeded its expansion from.
    """
    session = RecordingSession()
    repository = MemoryRepository(session, tenant_id=_TENANT)

    assert await repository.get_by_lexical_similarity(_USER, "the user") == []
    assert await repository.get_by_lexical_similarity(_USER, "yesterday's session") == []
    assert session.statements == []


async def test_lexical_query_never_sends_user_to_postgres() -> None:
    session = RecordingSession()
    repository = MemoryRepository(session, tenant_id=_TENANT)

    await repository.get_by_lexical_similarity(_USER, "the user budget")

    assert "websearch_to_tsquery('english', 'budget')" in session.sql[0]
    assert "'user'" not in session.sql[0]


async def test_no_shared_stopword_ever_reaches_postgres() -> None:
    """Generalises the `user` assertion to the whole shared vocabulary.

    `user` was the one that mattered because it is a constant in every title,
    but every word in the set is noise the tsquery cannot use, and each one that
    leaks back in widens the candidate set towards the whole corpus.
    """
    noise = sorted(LEXICAL_STOPWORDS)
    query = " ".join(noise + ["budget"])
    session = RecordingSession()
    repository = MemoryRepository(session, tenant_id=_TENANT)

    await repository.get_by_lexical_similarity(_USER, query)

    assert "websearch_to_tsquery('english', 'budget')" in session.sql[0]
    leaked = [word for word in noise if f"'{word}'" in session.sql[0]]
    assert leaked == []


async def test_lexical_sanitisation_is_unchanged() -> None:
    """Only `[a-z0-9]+` runs of two or more characters become query terms.

    The tsquery text is a bound parameter, so this is a hygiene boundary rather
    than an injection fix, and it must not quietly widen into regex or quotes.
    Punctuation is dropped rather than escaped, one-character runs are dropped,
    and the surviving terms are OR-joined once each.
    """
    session = RecordingSession()
    repository = MemoryRepository(session, tenant_id=_TENANT)

    await repository.get_by_lexical_similarity(_USER, "bud'; DROP TABLE memory_record-- OR x")

    sent = session.sql[0].split("websearch_to_tsquery('english', ")[1].split(")")[0]
    assert sent == "'bud OR drop OR table OR memory OR record'"
    assert "DROP TABLE" not in session.sql[0]


async def test_lexical_query_keeps_its_index_predicate_and_ranking() -> None:
    """The `@@` match, the flag-32 rank and the tenant scope are the contract."""
    session = RecordingSession()
    repository = MemoryRepository(session, tenant_id=_TENANT)

    await repository.get_by_lexical_similarity(_USER, "budget", limit=25)

    sql = session.sql[0]
    assert "search_vector @@ websearch_to_tsquery" in sql
    assert "ts_rank_cd" in sql
    assert "32" in sql
    assert "valid_to IS NULL" in sql
    assert f"organization_id = '{_TENANT}'" in sql
    assert "LIMIT" in sql


# ─── Task 2: ts_rank_cd is exposed instead of re-measured ────────────


async def test_lexical_search_result_carries_the_rank_it_was_ordered_by() -> None:
    current = make_record(title="the user distributed budget")
    other = make_record(title="the user has_baseline budget")
    session = RecordingSession(results=[[(current, 0.7619048), (other, 0.7368421)]])
    repository = MemoryRepository(session, tenant_id=_TENANT)

    result = await repository.get_by_lexical_similarity(
        _USER, "budget", include_ranks=True
    )

    assert isinstance(result, LexicalSearchResult)
    # Backward compatible: it is still the record sequence the old caller got.
    assert isinstance(result, Sequence)
    assert not isinstance(result, list)
    assert len(result) == 2
    assert [record.id for record in result] == [current.id, other.id]
    assert result[0] is current
    assert result.ranks == {
        current.id: pytest.approx(0.7619048),
        other.id: pytest.approx(0.7368421),
    }
    assert result.rank_for(current) == pytest.approx(0.7619048)
    assert result.rank_for(current.id) == pytest.approx(0.7619048)
    assert result.rank_for(uuid.uuid4()) == 0.0
    assert [record.id for record, _ in result.ranked] == [current.id, other.id]
    # Slicing keeps the type, so a caller can narrow a page and still read ranks.
    assert isinstance(result[:1], LexicalSearchResult)
    assert result[:1].rank_for(current) == pytest.approx(0.7619048)
    # The select gained the rank column, and only the rank column.
    assert "ts_rank_cd" in session.sql[0].split("FROM")[0]


async def test_lexical_search_defaults_to_the_bare_record_sequence() -> None:
    """The default call must keep the old shape: a list, no rank plumbing."""
    session = RecordingSession()
    repository = MemoryRepository(session, tenant_id=_TENANT)

    result = await repository.get_by_lexical_similarity(_USER, "budget")

    assert result == []
    assert not isinstance(result, LexicalSearchResult)
    # No extra select column, so the untouched call still costs one ts_rank_cd.
    assert "SELECT memory_record." in session.sql[0]


async def test_lexical_search_result_is_a_drop_in_for_the_existing_caller() -> None:
    """The engine's current call site must not notice the new return type.

    `engine._lexical_candidates` does `if records:` then a list comprehension
    over it, and `_graph_channel` seeds from `records[:limit]`. Every sequence
    protocol the engine can reach for has to keep working on the rank-bearing
    object without the engine being changed first.
    """
    first = make_record(title="the user distributed budget")
    second = make_record(title="the user has_baseline budget")
    session = RecordingSession(results=[[(first, 0.7), (second, 0.5)]])
    repository = MemoryRepository(session, tenant_id=_TENANT)

    result = await repository.get_by_lexical_similarity(_USER, "budget", include_ranks=True)

    assert bool(result) is True
    assert first in result
    assert result[0] is first
    assert result[-1] is second
    assert list(result) == [first, second]
    assert [memory for memory in result if memory.id == first.id] == [first]
    assert [record.id for record in result[:1]] == [first.id]
    assert list(reversed(result)) == [second, first]
    assert result.index(second) == 1
    assert result.count(first) == 1
    # Truthiness must not depend on the ranks: an all-zero page is still a page.
    zeroed = LexicalSearchResult([first], {first.id: 0.0})
    assert bool(zeroed) is True
    assert zeroed.rank_for(first) == 0.0
    assert not LexicalSearchResult([])


async def test_stopword_only_query_still_returns_a_rank_bearing_result() -> None:
    """The early return is a branch of the same contract, not an exception to it.

    A caller that asked for ranks and got a bare `[]` would have to re-check the
    type on the one path where there are no candidates.
    """
    session = RecordingSession()
    repository = MemoryRepository(session, tenant_id=_TENANT)

    result = await repository.get_by_lexical_similarity(
        _USER, "the user", include_ranks=True
    )

    assert isinstance(result, LexicalSearchResult)
    assert list(result) == []
    assert result.ranks == {}
    assert result.ranked == []
    assert session.statements == []


def test_lexical_search_result_ranks_survive_a_reslice_that_excludes_a_row() -> None:
    """Ranks are keyed by id, so narrowing a page cannot misalign a score.

    The alternative -- one parallel list of floats -- silently attaches the
    top score to the wrong memory the first time a caller slices or filters.
    """
    kept = make_record(title="the user distributed budget")
    dropped = make_record(title="the user has_baseline budget")

    page = LexicalSearchResult([kept, dropped], {kept.id: 0.7, dropped.id: 0.5})[:1]

    assert [record.id for record in page] == [kept.id]
    assert page.ranks == {kept.id: pytest.approx(0.7)}


# ─── Task 3: the graph route must not publish superseded facts ────────


async def test_get_linked_to_entities_excludes_superseded_rows() -> None:
    current = make_record(entity_ids=frozenset({_ENTITY}))
    superseded = make_record(
        valid_to=datetime.now(UTC),
        entity_ids=frozenset({_ENTITY}),
        title="the user moved Mumbai",
    )
    session = RecordingSession(rows=[current, superseded])
    repository = MemoryRepository(session, tenant_id=_TENANT)

    rows = await repository.get_linked_to_entities([_ENTITY], user_id=_USER)

    assert [row.id for row in rows] == [current.id]
    assert "valid_to IS NULL" in session.sql[0]


async def test_get_linked_to_entities_response_shape_is_unchanged() -> None:
    """The route publishes stored `content` verbatim, so rows stay unhydrated."""
    row = make_record(entity_ids=frozenset({_ENTITY}), content="enc:v1:ciphertext")
    session = RecordingSession(rows=[row])
    repository = MemoryRepository(session, tenant_id=_TENANT)

    rows = await repository.get_linked_to_entities([_ENTITY])

    assert rows == [row]
    assert rows[0].content == "enc:v1:ciphertext"
    assert rows[0].title == row.title
    assert rows[0].created_at == row.created_at


async def test_get_linked_to_entities_stays_tenant_scoped() -> None:
    mine = make_record(entity_ids=frozenset({_ENTITY}))
    theirs = make_record(organization_id=_OTHER_TENANT, entity_ids=frozenset({_ENTITY}))
    session = RecordingSession(rows=[mine, theirs])
    repository = MemoryRepository(session, tenant_id=_TENANT)

    assert [row.id for row in await repository.get_linked_to_entities([_ENTITY])] == [mine.id]
    assert f"organization_id = '{_TENANT}'" in session.sql[0]


async def test_get_linked_to_entities_skips_the_query_for_no_entities() -> None:
    session = RecordingSession()
    repository = MemoryRepository(session, tenant_id=_TENANT)

    assert await repository.get_linked_to_entities([]) == []
    assert session.statements == []


# ─── Task 4: one validity-filtered bulk link read for the graph walk ──


async def test_bulk_current_memory_ids_excludes_superseded_memories() -> None:
    current = make_record(entity_ids=frozenset({_ENTITY}))
    superseded = make_record(valid_to=datetime.now(UTC), entity_ids=frozenset({_ENTITY}))
    session = RecordingSession(rows=[current, superseded], project=as_link_pairs)
    repository = MemoryEntityLinkRepository(session, tenant_id=_TENANT)

    grouped = await repository.bulk_current_memory_ids_by_entity([_ENTITY])

    assert grouped == {_ENTITY: [current.id]}
    assert "valid_to IS NULL" in session.sql[0]
    assert "JOIN memory_record ON" in session.sql[0]


async def test_bulk_current_memory_ids_is_tenant_scoped_on_both_sides() -> None:
    mine = make_record(entity_ids=frozenset({_ENTITY}))
    theirs = make_record(organization_id=_OTHER_TENANT, entity_ids=frozenset({_ENTITY}))
    session = RecordingSession(rows=[mine, theirs], project=as_link_pairs)
    repository = MemoryEntityLinkRepository(session, tenant_id=_TENANT)

    grouped = await repository.bulk_current_memory_ids_by_entity([_ENTITY, _OTHER_ENTITY])

    assert grouped == {_ENTITY: [mine.id]}
    # Once for the link row, once for the memory row whose validity is trusted.
    assert session.sql[0].count(f"'{_TENANT}'") >= 2


async def test_bulk_current_memory_ids_groups_per_entity() -> None:
    first, second = uuid.uuid4(), uuid.uuid4()
    session = RecordingSession(
        results=[[(_ENTITY, first), (_OTHER_ENTITY, second), (_ENTITY, second)]],
    )
    repository = MemoryEntityLinkRepository(session, tenant_id=_TENANT)

    grouped = await repository.bulk_current_memory_ids_by_entity([_ENTITY, _OTHER_ENTITY])

    assert grouped == {_ENTITY: [first, second], _OTHER_ENTITY: [second]}
    assert "ORDER BY" in session.sql[0]


async def test_bulk_current_memory_ids_reads_two_columns_and_nothing_else() -> None:
    """The point of the method is that it does not hydrate a MemoryRecord.

    The engine needs a count per entity to weight graph degree, not the rows.
    Selecting the model would pull `content` and both 1024-dim embedding columns
    for every linked memory -- the exact cost this method exists to avoid -- and
    the regression is invisible to the row assertions above because the fixture
    project feeds back whatever the select claims to return.
    """
    session = RecordingSession(results=[[]])
    repository = MemoryEntityLinkRepository(session, tenant_id=_TENANT)

    await repository.bulk_current_memory_ids_by_entity([_ENTITY])

    projected = session.sql[0].split("FROM")[0]
    assert projected.strip() == "SELECT memory_entity_link.entity_id, memory_entity_link.memory_id"


async def test_bulk_current_memory_ids_omits_entities_with_no_current_link() -> None:
    """Absent, not empty: a zero default is the caller's, not a lie from here."""
    session = RecordingSession(results=[[]])
    repository = MemoryEntityLinkRepository(session, tenant_id=_TENANT)

    assert await repository.bulk_current_memory_ids_by_entity([_ENTITY]) == {}


async def test_bulk_current_memory_ids_trusts_the_memory_side_tenant() -> None:
    """A link stamped with my org can still point at another org's memory.

    `memory_entity_link.organization_id` is a denormalised copy that no foreign
    key enforces, so scoping only the link row leaves a cross-tenant read
    available. The memory row is the one whose validity is trusted, so it has to
    be scoped too.
    """
    mine = make_record(entity_ids=frozenset({_ENTITY}))
    # A link that claims my tenant but resolves to another tenant's memory.
    theirs = make_record(organization_id=_OTHER_TENANT, entity_ids=frozenset({_ENTITY}))
    session = RecordingSession(rows=[mine, theirs], project=as_link_pairs)
    repository = MemoryEntityLinkRepository(session, tenant_id=_TENANT)

    grouped = await repository.bulk_current_memory_ids_by_entity([_ENTITY])

    assert grouped == {_ENTITY: [mine.id]}
    assert "memory_record.organization_id" in session.sql[0]


async def test_bulk_current_memory_ids_skips_the_query_for_no_entities() -> None:
    session = RecordingSession()
    repository = MemoryEntityLinkRepository(session, tenant_id=_TENANT)

    assert await repository.bulk_current_memory_ids_by_entity([]) == {}
    assert session.statements == []


async def test_bulk_get_memories_for_entities_is_left_alone() -> None:
    """The engine is calling this today; it must keep counting every link."""
    link = make_link()
    session = RecordingSession(results=[[link]])
    repository = MemoryEntityLinkRepository(session, tenant_id=_TENANT)

    assert list(await repository.bulk_get_memories_for_entities([_ENTITY])) == [link]
    assert "valid_to" not in session.sql[0]
    assert "JOIN" not in session.sql[0]


# ─── Task 5: the fallback read and the dense metadata predicate ───────


async def test_get_by_user_excludes_superseded_rows() -> None:
    current = make_record()
    superseded = make_record(valid_to=datetime.now(UTC))
    session = RecordingSession(rows=[current, superseded])
    repository = MemoryRepository(session, tenant_id=_TENANT)

    assert [row.id for row in await repository.get_by_user(_USER)] == [current.id]
    assert "valid_to IS NULL" in session.sql[0]


async def test_get_by_user_orders_deterministically() -> None:
    """A truncated fallback page must not depend on Postgres' row order."""
    session = RecordingSession()
    repository = MemoryRepository(session, tenant_id=_TENANT)

    await repository.get_by_user(_USER, limit=1000)

    assert "ORDER BY memory_record.created_at DESC, memory_record.id ASC" in session.sql[0]
    assert "LIMIT" in session.sql[0]
    assert "OFFSET" in session.sql[0]


async def test_get_by_user_keeps_validity_ordering_and_scope_on_one_statement() -> None:
    """They are one question, so they have to be one statement.

    Asserted together because each is independently satisfied by the other's
    absence: dropping the ORDER BY still returns the right rows, and dropping the
    validity filter still returns the right rows for a corpus with no
    corrections in it.
    """
    current = make_record()
    superseded = make_record(valid_to=datetime.now(UTC))
    theirs = make_record(organization_id=_OTHER_TENANT)
    session = RecordingSession(rows=[current, superseded, theirs])
    repository = MemoryRepository(session, tenant_id=_TENANT)

    rows = await repository.get_by_user(_USER, limit=500)

    assert [row.id for row in rows] == [current.id]
    sql = session.sql[0]
    assert "memory_record.valid_to IS NULL" in sql
    assert "ORDER BY memory_record.created_at DESC, memory_record.id ASC" in sql
    assert f"memory_record.user_id = '{_USER}'" in sql
    assert f"memory_record.organization_id = '{_TENANT}'" in sql


async def test_get_by_user_bounds_an_unbounded_limit() -> None:
    """`limit=None` must become a bounded read, not an unbounded table scan.

    The MCP and route callers pass explicit limits, but a repository method
    whose default is unbounded is one refactor away from a full scan on the
    fallback path that runs on every retrieval request.
    """
    session = RecordingSession()
    repository = MemoryRepository(session, tenant_id=_TENANT)

    await repository.get_by_user(_USER, limit=None)

    assert f"LIMIT {MemoryRepository._DEFAULT_PAGE_LIMIT}" in session.sql[0]


async def test_dense_metadata_predicate_ignores_model_and_version_drift() -> None:
    """A version bump must not silently empty the dense channel.

    The predicate is the vector space -- profile plus width -- because that is
    what decides which column holds comparable numbers. Model and version drift
    is reported, not filtered on.
    """
    session = RecordingSession(results=[[], [], [[0, 0, 0]]])
    repository = MemoryRepository(session, tenant_id=_TENANT)

    await repository.get_by_vector_similarity(
        _USER,
        [0.0] * OFFLINE_EMBEDDING_PROFILE.dimensions,
        limit=10,
        profile=OFFLINE_EMBEDDING_PROFILE,
    )

    where_clause = session.sql[1].split("WHERE", 1)[1]
    assert "embedding_profile = 'offline-qwen3-1024'" in where_clause
    assert "embedding_dimensions = 1024" in where_clause
    assert "embedding_model =" not in where_clause
    assert "embedding_version =" not in where_clause
    # The other vector column staying empty is still a hard requirement.
    assert "embedding IS NULL" in where_clause
    assert "embedding_1024 IS NOT NULL" in where_clause


async def test_dense_legacy_path_widens_only_over_unlabelled_rows() -> None:
    """`include_legacy` opts into rows with no metadata, not into any model.

    Widening to `OR` over model/version would put vectors from a different
    encoder into the same ranking, which is the silent corruption the narrow
    predicate was protecting against; the unlabelled legacy rows are the ones
    with no encoder identity to violate.
    """
    session = RecordingSession(results=[[], [], [[0, 0, 0]]])
    repository = MemoryRepository(session, tenant_id=_TENANT)

    await repository.get_by_vector_similarity(
        _USER,
        [0.0] * OFFLINE_EMBEDDING_PROFILE.dimensions,
        limit=10,
        profile=OFFLINE_EMBEDDING_PROFILE,
        include_legacy=True,
    )

    where_clause = session.sql[1].split("WHERE", 1)[1]
    assert "embedding_profile IS NULL" in where_clause
    assert "embedding_model IS NULL" in where_clause
    assert "embedding_version IS NULL" in where_clause
    assert "embedding_model =" not in where_clause
    assert "embedding_version =" not in where_clause


async def test_dense_empty_result_reports_embedding_metadata_drift(caplog) -> None:
    session = RecordingSession(results=[[], [], [[3, 0, 0]]])
    repository = MemoryRepository(session, tenant_id=_TENANT)

    with caplog.at_level(logging.WARNING, logger="contexta.repositories.memory_repo"):
        rows = await repository.get_by_vector_similarity(
            _USER,
            [0.0] * OFFLINE_EMBEDDING_PROFILE.dimensions,
            limit=10,
            profile=OFFLINE_EMBEDDING_PROFILE,
        )

    assert rows == []
    drift = [entry for entry in caplog.records if "different embedding model/version" in entry.message]
    assert len(drift) == 1
    assert "3 stored vectors" in drift[0].message


async def test_dense_empty_result_reports_a_foreign_vector_space(caplog) -> None:
    """An online corpus queried with the offline profile has to be sayable.

    The stored vector is in `embedding` (1536), not in the queried column, so a
    probe scoped to the queried column reports an empty tenant and says nothing
    -- which is the failure this whole diagnostic exists to remove.
    """
    session = RecordingSession(results=[[], [], [[0, 7, 0]]])
    repository = MemoryRepository(session, tenant_id=_TENANT)

    with caplog.at_level(logging.WARNING, logger="contexta.repositories.memory_repo"):
        await repository.get_by_vector_similarity(
            _USER,
            [0.0] * OFFLINE_EMBEDDING_PROFILE.dimensions,
            limit=10,
            profile=OFFLINE_EMBEDDING_PROFILE,
        )

    foreign = [entry for entry in caplog.records if "another embedding profile" in entry.message]
    assert len(foreign) == 1
    assert "7 stored vectors" in foreign[0].message
    # Both columns are part of "this tenant has vectors".
    assert "memory_record.embedding IS NOT NULL" in session.sql[2]
    assert "memory_record.embedding_1024 IS NOT NULL" in session.sql[2]


async def test_dense_probe_is_only_issued_when_the_query_found_nothing() -> None:
    """A normal hit costs the query and nothing else."""
    hit = make_record()
    session = RecordingSession(results=[[], [hit], [[0, 0, 0]]])
    repository = MemoryRepository(session, tenant_id=_TENANT)

    rows = await repository.get_by_vector_similarity(
        _USER,
        [0.0] * OFFLINE_EMBEDDING_PROFILE.dimensions,
        limit=10,
        profile=OFFLINE_EMBEDDING_PROFILE,
    )

    assert [record.id for record in rows] == [hit.id]
    assert len(session.statements) == 2


async def test_dense_genuinely_empty_space_warns_about_nothing(caplog) -> None:
    """An empty corpus is not drift, and must not be dressed up as drift."""
    session = RecordingSession(results=[[], [], [[0, 0, 0]]])
    repository = MemoryRepository(session, tenant_id=_TENANT)

    with caplog.at_level(logging.WARNING, logger="contexta.repositories.memory_repo"):
        rows = await repository.get_by_vector_similarity(
            _USER,
            [0.0] * OFFLINE_EMBEDDING_PROFILE.dimensions,
            limit=10,
            profile=OFFLINE_EMBEDDING_PROFILE,
        )

    assert rows == []
    assert not [entry for entry in caplog.records if entry.levelno >= logging.WARNING]


async def test_dense_drift_probe_failure_never_breaks_the_query(caplog) -> None:
    class BrokenProbeSession(RecordingSession):
        async def execute(self, statement: Any) -> FakeResult:
            self.statements.append(statement)
            self.sql.append(render(statement))
            if len(self.statements) < 3:  # hnsw GUCs, then the vector query
                return FakeResult([])
            raise RuntimeError("probe exploded")

    session = BrokenProbeSession()
    repository = MemoryRepository(session, tenant_id=_TENANT)

    with caplog.at_level(logging.WARNING, logger="contexta.repositories.memory_repo"):
        assert await repository.get_by_vector_similarity(
            _USER,
            [0.0] * OFFLINE_EMBEDDING_PROFILE.dimensions,
            limit=10,
            profile=OFFLINE_EMBEDDING_PROFILE,
        ) == []
    assert not [entry for entry in caplog.records if entry.levelno >= logging.WARNING]
