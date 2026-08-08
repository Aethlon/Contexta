"""Tests for contexta.core.schemas Pydantic models."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from contexta.core.schemas import (
    ContextConfig,
    ContextRequest,
    ExtractedMemory,
    ImportanceSignals,
    ObservationPayload,
    RetrievalQuery,
    TokenAllocation,
)
from contexta.core.types import MemoryType, SourceType


class TestObservationPayload:
    """Verify ObservationPayload validation and defaults."""

    def test_valid_payload(self) -> None:
        payload = ObservationPayload(
            user_id=uuid4(),
            organization_id=uuid4(),
            session_id=uuid4(),
            messages=[{"role": "user", "content": "hello"}],
        )
        assert payload.metadata is None
        assert payload.policy is None

    def test_with_optional_fields(self) -> None:
        payload = ObservationPayload(
            user_id=uuid4(),
            organization_id=uuid4(),
            session_id=uuid4(),
            messages=[{"role": "user", "content": "hi"}],
            metadata={"source": "sdk"},
            policy="coding-agent",
        )
        assert payload.metadata == {"source": "sdk"}
        assert payload.policy == "coding-agent"

    def test_missing_user_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            ObservationPayload(
                organization_id=uuid4(),
                session_id=uuid4(),
                messages=[{"role": "user", "content": "hi"}],
            )

    def test_missing_messages_raises(self) -> None:
        with pytest.raises(ValidationError):
            ObservationPayload(
                user_id=uuid4(),
                organization_id=uuid4(),
                session_id=uuid4(),
            )

    def test_invalid_uuid_raises(self) -> None:
        with pytest.raises(ValidationError):
            ObservationPayload(
                user_id="not-a-uuid",
                organization_id=uuid4(),
                session_id=uuid4(),
                messages=[],
            )


class TestExtractedMemory:
    """Verify ExtractedMemory validation and defaults."""

    def test_valid_memory(self) -> None:
        mem = ExtractedMemory(
            memory_type=MemoryType.FACT,
            source_type=SourceType.USER_EXPLICIT,
            title="User prefers Python",
            content="The user stated they prefer Python over JavaScript.",
        )
        assert mem.structured_data is None
        assert mem.tags == []
        assert mem.entities == []
        assert mem.has_emphasis is False
        assert mem.impacts_decisions is False

    def test_empty_title_raises(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedMemory(
                memory_type=MemoryType.FACT,
                source_type=SourceType.USER_EXPLICIT,
                title="",
                content="some content",
            )

    def test_invalid_memory_type_raises(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedMemory(
                memory_type="invalid_type",
                source_type=SourceType.USER_EXPLICIT,
                title="Test",
                content="content",
            )

    def test_with_all_fields(self) -> None:
        mem = ExtractedMemory(
            memory_type=MemoryType.PROJECT,
            source_type=SourceType.TOOL_OUTPUT,
            title="contexta project",
            content="Working on contexta memory engine",
            structured_data={"repo": "contexta", "language": "python"},
            tags=["python", "ai"],
            entities=["contexta", "Python"],
            has_emphasis=True,
            impacts_decisions=True,
        )
        assert mem.structured_data == {"repo": "contexta", "language": "python"}
        assert mem.tags == ["python", "ai"]
        assert mem.entities == ["contexta", "Python"]


class TestImportanceSignals:
    """Verify ImportanceSignals validation and defaults."""

    def test_defaults(self) -> None:
        signals = ImportanceSignals()
        assert signals.mention_count == 0
        assert signals.last_referenced is None
        assert signals.has_emphasis is False
        assert signals.impacts_decisions is False
        assert signals.utility_ratio is None

    def test_negative_mention_count_raises(self) -> None:
        with pytest.raises(ValidationError):
            ImportanceSignals(mention_count=-1)

    def test_utility_ratio_out_of_range_raises(self) -> None:
        with pytest.raises(ValidationError):
            ImportanceSignals(utility_ratio=1.5)

        with pytest.raises(ValidationError):
            ImportanceSignals(utility_ratio=-0.1)


class TestTokenAllocation:
    """Verify TokenAllocation validation."""

    def test_valid_allocation(self) -> None:
        alloc = TokenAllocation(
            total_budget=4000,
            allocations={"projects": 1400, "goals": 800},
            actual_usage={"projects": 1200, "goals": 750},
        )
        assert alloc.total_budget == 4000

    def test_zero_budget_raises(self) -> None:
        with pytest.raises(ValidationError):
            TokenAllocation(total_budget=0)

    def test_negative_budget_raises(self) -> None:
        with pytest.raises(ValidationError):
            TokenAllocation(total_budget=-100)


class TestRetrievalQuery:
    """Verify RetrievalQuery validation and defaults."""

    def test_valid_query(self) -> None:
        query = RetrievalQuery(
            user_id=uuid4(),
            organization_id=uuid4(),
            query_text="What projects am I working on?",
        )
        assert query.limit == 20
        assert query.graph_depth == 2
        assert query.include_cold is True
        assert query.include_archived is False
        assert query.memory_types is None
        assert query.tags is None

    def test_empty_query_text_raises(self) -> None:
        with pytest.raises(ValidationError):
            RetrievalQuery(
                user_id=uuid4(),
                organization_id=uuid4(),
                query_text="",
            )

    def test_limit_bounds(self) -> None:
        with pytest.raises(ValidationError):
            RetrievalQuery(
                user_id=uuid4(),
                organization_id=uuid4(),
                query_text="test",
                limit=0,
            )
        with pytest.raises(ValidationError):
            RetrievalQuery(
                user_id=uuid4(),
                organization_id=uuid4(),
                query_text="test",
                limit=101,
            )

    def test_with_memory_type_filter(self) -> None:
        query = RetrievalQuery(
            user_id=uuid4(),
            organization_id=uuid4(),
            query_text="test",
            memory_types=[MemoryType.FACT, MemoryType.PREFERENCE],
        )
        assert query.memory_types == [MemoryType.FACT, MemoryType.PREFERENCE]


class TestContextConfig:
    """Verify ContextConfig validation and defaults."""

    def test_defaults(self) -> None:
        config = ContextConfig()
        assert config.num_recent_messages == 10
        assert config.num_relevant_memories == 20
        assert config.graph_depth == 2
        assert config.include_user_model is True
        assert config.token_budget is None
        assert config.custom_weights is None

    def test_custom_values(self) -> None:
        config = ContextConfig(
            num_recent_messages=5,
            num_relevant_memories=50,
            graph_depth=3,
            include_user_model=False,
            token_budget=8000,
            custom_weights={"projects": 0.5, "goals": 0.3, "facts": 0.2},
        )
        assert config.token_budget == 8000
        assert config.custom_weights["projects"] == 0.5


class TestContextRequest:
    """Verify ContextRequest validation and defaults."""

    def test_valid_request(self) -> None:
        req = ContextRequest(
            user_id=uuid4(),
            organization_id=uuid4(),
            session_id=uuid4(),
        )
        assert req.config.num_recent_messages == 10

    def test_with_custom_config(self) -> None:
        req = ContextRequest(
            user_id=uuid4(),
            organization_id=uuid4(),
            session_id=uuid4(),
            config=ContextConfig(token_budget=4000),
        )
        assert req.config.token_budget == 4000
