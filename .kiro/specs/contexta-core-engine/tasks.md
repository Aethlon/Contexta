# Implementation Plan: contexta Core Engine

## Overview

Implement the contexta Core Engine — a Python-based memory intelligence pipeline for AI agents. The implementation follows an incremental approach: project scaffolding and data models first, then core pipeline components (extraction, scoring, storage), followed by advanced subsystems (decay, reflection, dream cycle), and finally integration wiring. All code uses Python 3.11+, FastAPI, SQLAlchemy 2.0, PostgreSQL+pgvector, Redis, Celery, and Hypothesis for property-based testing.

## Tasks

- [x] 1. Project scaffolding and configuration
  - [x] 1.1 Create project directory structure and configuration
    - Create the `contexta/` package structure as defined in the design (api/, core/, models/, repositories/, services/, workers/, config/, migrations/)
    - Create `pyproject.toml` with dependencies: fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, redis, celery, pgvector, hypothesis, pytest, alembic, pydantic
    - Create `contexta/config/settings.py` with Pydantic BaseSettings for database URL, Redis URL, embedding model, LLM provider, and feature flags
    - _Requirements: All (foundational)_

  - [x] 1.2 Define core enums, data types, and base error classes
    - Create `contexta/core/types.py` with MemoryType, SourceType, MemoryState, EntityType, RelationType, UsageSignal enums
    - Create `contexta/core/schemas.py` with Pydantic models: ObservationPayload, ExtractedMemory, ImportanceSignals, TokenAllocation, RetrievalQuery, ContextRequest, ContextConfig
    - Create `contexta/core/errors.py` with contextaError, ValidationError, AuthorizationError, ExtractionError, StorageError
    - _Requirements: 2.2, 2.3, 4.4, 4.5, 20.1_

  - [x] 1.3 Create SQLAlchemy models and Alembic migration
    - Create `contexta/models/memory.py` with MemoryRecord model (all fields from design ERD including pgvector column)
    - Create `contexta/models/entity.py` with Entity, EntityEdge, MemoryEntityLink models
    - Create `contexta/models/session.py` with Session model
    - Create `contexta/models/audit.py` with AuditLog model
    - Create `contexta/models/policy.py` with MemoryPolicy model
    - Create `contexta/models/schema.py` with CustomSchema model
    - Create `contexta/models/cluster.py` with SemanticCluster, ClusterMembership models
    - Create `contexta/models/feedback.py` with RetrievalFeedback model
    - Create `contexta/models/compression.py` with CompressedSummary model
    - Create `contexta/models/version.py` with MemoryVersion model
    - Create `contexta/models/dream.py` with MissingMemoryCandidate model
    - Create initial Alembic migration with all tables and indexes (HNSW, B-tree, GIN tsvector)
    - _Requirements: 7.1, 7.2, 7.4, 7.5, 14.1, 14.5, 22.7, 24.2, 25.1_

  - [x] 1.4 Create base repository with tenant isolation
    - Create `contexta/repositories/base.py` with TenantScopedRepository base class that enforces organization_id filtering on all queries
    - Implement query interceptor that automatically adds WHERE organization_id = :tenant_id to all SELECT, UPDATE, DELETE operations
    - Create `contexta/repositories/memory_repo.py`, `entity_repo.py`, `session_repo.py`, `audit_repo.py` extending base
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [-]* 1.5 Write property tests for tenant isolation (Property 16)
    - **Property 16: Tenant isolation**
    - Verify that for any query on behalf of tenant A, all returned records have organization_id equal to A
    - Verify that write operations where authenticated org_id does not match target org_id are rejected
    - Use Hypothesis strategies: two random UUIDs for org_ids, random memory/entity records
    - **Validates: Requirements 7.3, 8.7, 14.1, 14.2, 14.3, 14.4, 16.5, 19.7, 22.8, 25.8**

- [ ] 2. Observation Engine and sensitive data filtering
  - [x] 2.1 Implement observation payload validation
    - Create `contexta/api/routes/observations.py` with POST /observations and POST /observations/batch endpoints
    - Implement payload size validation (1MB max) returning 422 with size error
    - Implement required field validation (user_id, organization_id, session_id, messages) returning 422 with field-level errors
    - Implement tenant association from authenticated context
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6_

  - [-]* 2.2 Write property tests for payload validation (Properties 1, 2)
    - **Property 1: Observation payload validation boundary**
    - Verify payloads > 1MB are rejected, payloads <= 1MB with valid fields are accepted
    - **Property 2: Observation payload field validation**
    - Verify missing required fields produce validation errors specifying invalid fields
    - Use Hypothesis: `st.binary()` for size testing, selective field omission strategies
    - **Validates: Requirements 1.3, 1.4, 1.5**

  - [x] 2.3 Implement sensitive data filtering and redaction
    - Create `contexta/core/extraction/sensitive_filter.py` with pattern-based detection for passwords, OTPs, payment card numbers, API secrets, tokens, session cookies
    - Implement redaction that replaces detected patterns with `[REDACTED]` placeholder
    - Integrate primary scan into observation ingestion (before enqueue)
    - Implement secondary scan in extraction worker (after LLM extraction)
    - If secondary scan detects sensitive data, discard memory and log security event
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [-]* 2.4 Write property tests for sensitive data redaction (Property 3)
    - **Property 3: Sensitive data redaction completeness**
    - Verify that for any text containing embedded sensitive patterns, after redaction the output does NOT contain the original sensitive value
    - Use Hypothesis: custom strategy generating text with embedded secrets (API keys, passwords, card numbers)
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

  - [x] 2.5 Implement observation enqueue to Redis Streams
    - Create `contexta/workers/celery_app.py` with Celery configuration using Redis broker
    - Create `contexta/workers/extraction_tasks.py` with task to process enqueued observations
    - Wire observation API to enqueue validated+redacted payloads as Celery tasks
    - Return 202 Accepted with job reference after successful enqueue
    - _Requirements: 1.2, 2.5_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Memory extraction and classification
  - [x] 4.1 Implement extraction worker with LLM-based extraction
    - Create `contexta/core/extraction/worker.py` with ExtractionWorker class
    - Implement LLM-based extraction that produces typed memories (fact, preference, goal, project, skill, relationship, event, episodic, pattern, contact, custom)
    - Implement memory_type classification from MemoryType enum
    - Implement source_type assignment based on observation origin
    - Generate title and structured_data for each extracted memory
    - Handle extraction failures: log diagnostics, mark job as failed
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 4.2 Write property tests for extraction type invariants (Property 4)
    - **Property 4: Extracted memory type invariant**
    - Verify memory_type is always a valid MemoryType enum member
    - Verify source_type is always a valid SourceType enum member
    - Verify title is always a non-empty string
    - Use Hypothesis: mock LLM responses with various extraction outputs
    - **Validates: Requirements 2.2, 2.3, 2.4**

  - [x] 4.3 Implement memory deduplication
    - Create deduplication logic in `contexta/core/extraction/worker.py` or separate module
    - Implement semantic similarity comparison against existing memories (same user_id, org_id, memory_type)
    - If similarity > 0.95: discard new memory, update existing memory timestamp
    - If similarity in [0.85, 0.95]: merge new information into existing memory
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [ ]* 4.4 Write property tests for deduplication (Properties 21, 22)
    - **Property 21: Deduplication threshold behavior**
    - Verify similarity > 0.95 → duplicate discard; similarity in [0.85, 0.95] → merge
    - **Property 22: Deduplication scope invariant**
    - Verify comparisons only occur within same user_id, organization_id, and memory_type
    - Use Hypothesis: `st.floats(0, 1)` for similarity scores, random memory pairs
    - **Validates: Requirements 10.2, 10.3, 10.4, 10.5**

- [ ] 5. Entity resolution and graph management
  - [x] 5.1 Implement entity resolver
    - Create `contexta/core/entities/resolver.py` with EntityResolver class
    - Implement entity matching using semantic + name similarity with 0.8 confidence threshold
    - If confidence > 0.8: link memory to existing entity
    - If confidence <= 0.8: create new entity node
    - Support entity types: Project, Person, Company, Technology, Preference, Goal, Skill, Topic
    - Create typed edges: USES, WORKS_ON, LIKES, DEPENDS_ON, OWNS, SUPERSEDED_BY, RELATED_TO
    - Update entity last_updated timestamp on resolution
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 5.2 Write property tests for entity resolution (Properties 5, 6)
    - **Property 5: Entity resolution threshold**
    - Verify confidence > 0.8 → link to existing; confidence <= 0.8 → create new
    - **Property 6: Entity timestamp monotonicity**
    - Verify entity last_updated >= observation timestamp that triggered resolution
    - Use Hypothesis: `st.floats(0, 1)` for confidence, `st.datetimes()` for timestamps
    - **Validates: Requirements 4.2, 4.3, 4.6, 23.3**

  - [x] 5.3 Implement entity state manager
    - Create `contexta/core/entities/state_manager.py` with EntityStateManager class
    - Maintain state record: entity_type, name, summary, status, last_updated, aggregated_attributes
    - Update entity summary and last_updated when new memory is linked
    - Compute aggregated_attributes from associated facts, preferences, relationships
    - Transition entity to inactive after 90 days without observations
    - Support status transitions: active → inactive → archived, inactive → active
    - _Requirements: 23.1, 23.2, 23.3, 23.4, 23.5, 23.6, 23.7, 23.8_

  - [ ]* 5.4 Write property tests for entity state (Properties 39, 40)
    - **Property 39: Entity state transition validity**
    - Verify only valid transitions: active → inactive → archived, inactive → active
    - **Property 40: Entity inactivity transition**
    - Verify entities with last_updated > 90 days ago transition to inactive
    - Use Hypothesis: `st.sampled_from` for states, `st.datetimes()` for timestamps
    - **Validates: Requirements 23.5, 23.7**

- [ ] 6. Truth maintenance and contradiction resolution
  - [x] 6.1 Implement truth maintenance engine
    - Create `contexta/core/truth/maintenance.py` with TruthMaintenanceEngine class
    - Compare new memory against existing memories for same entity and memory_type
    - On contradiction: set existing memory valid_to, create SUPERSEDED_BY edge, preserve old in memory_versions
    - Maintain current truth (valid_to is null) vs historical truth (valid_to set) partition
    - Log contradiction events with old and new memory content
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 6.2 Write property tests for truth maintenance (Properties 7, 8)
    - **Property 7: Supersession invariants**
    - Verify: old memory valid_to is non-null, SUPERSEDED_BY edge exists, memory_version preserves old content
    - **Property 8: Current vs historical truth partition**
    - Verify every memory is either current (valid_to null) or historical (valid_to set) — mutually exclusive and exhaustive
    - Use Hypothesis: random memory pairs with contradicting content
    - **Validates: Requirements 5.2, 5.3, 5.4, 5.5**

- [ ] 7. Memory scoring engine and importance framework
  - [x] 7.1 Implement importance framework
    - Create `contexta/core/scoring/importance.py` with ImportanceFramework class
    - Implement BASE_SCORES mapping for all 11 memory types
    - Implement modifiers: repetition (+0.1 max at 3+ sessions), recency (+0.05 within 7 days), emphasis (+0.15), decision-impact (+0.1 max), utility (±0.1)
    - Clamp final score to [0.0, 1.0]
    - Implement low-value content detection (greetings, small talk, filler) → reject from storage
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.9_

  - [ ]* 7.2 Write property tests for importance framework (Properties 9, 10, 11, 12)
    - **Property 9: Importance score clamping**
    - Verify final importance is always in [0.0, 1.0] regardless of modifier combinations
    - **Property 10: Importance base score mapping**
    - Verify each memory_type maps to its defined base score
    - **Property 11: Importance modifier bounds**
    - Verify each modifier is individually bounded: repetition [0, 0.1], recency [0, 0.05], emphasis 0.15, decision-impact [0, 0.1], utility [-0.1, 0.1]
    - **Property 12: Low-value content rejection**
    - Verify low-value patterns (greetings, small talk) are classified as low-value and rejected
    - Use Hypothesis: `st.sampled_from(MemoryType)`, random ImportanceSignals, text with low-value patterns
    - **Validates: Requirements 6.1, 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8**

  - [x] 7.3 Implement memory scoring engine
    - Create `contexta/core/scoring/engine.py` with MemoryScoringEngine class
    - Implement compute_importance delegating to ImportanceFramework
    - Implement compute_confidence with static mapping: user_explicit=1.0, tool_output=0.8, agent_inference=0.6, imported_file=0.7, api=0.7
    - Implement compute_freshness with time-decay function (monotonically decreasing with age)
    - Implement compute_utility as usage_count / retrieval_count bounded in [0.0, 1.0]
    - Recompute freshness on retrieval (not stored statically)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 7.4 Write property tests for scoring engine (Properties 13, 14, 15)
    - **Property 13: Confidence score determinism**
    - Verify source_type → confidence is deterministic: user_explicit=1.0, tool_output=0.8, agent_inference=0.6, imported_file=0.7, api=0.7
    - **Property 14: Freshness monotonic decay**
    - Verify for any two memories where A is older than B, freshness(A) <= freshness(B)
    - **Property 15: Utility ratio computation**
    - Verify utility = usage_count / retrieval_count, bounded [0.0, 1.0]; positive signal doesn't decrease utility; ignored signal doesn't increase utility
    - Use Hypothesis: `st.sampled_from(SourceType)`, pairs of `st.datetimes()`, `st.integers(min_value=0)` for counts
    - **Validates: Requirements 6.2, 6.3, 6.4, 6.5, 22.2, 22.3, 22.4**

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Memory storage and embedding generation
  - [x] 9.1 Implement memory storage pipeline
    - Create `contexta/repositories/memory_repo.py` with full CRUD operations
    - Implement persist method storing all required fields (id, user_id, org_id, memory_type, title, content, structured_data, source_type, confidence, importance, tags, session_id, created_at, updated_at, valid_from)
    - Implement graph edge storage in entity_edge table
    - Implement keyword indexing via PostgreSQL tsvector on title, content, tags
    - Implement pinned memory handling (is_pinned=true excludes from decay)
    - _Requirements: 7.1, 7.2, 7.4, 7.5, 7.6_

  - [x] 9.2 Implement embedding service
    - Create `contexta/services/embedding.py` with EmbeddingService class
    - Generate vector embeddings from memory title + content using configurable provider
    - Store embeddings in pgvector column on memory_record
    - Regenerate embedding on memory update
    - Process embedding generation asynchronously (Celery task)
    - Graceful degradation: store memory without embedding if service unavailable, enqueue for later
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

- [ ] 10. Policy engine and schema registry
  - [x] 10.1 Implement policy engine
    - Create `contexta/core/policy/engine.py` with PolicyEngine class
    - Implement register_policy for named policy profiles (tenant-scoped)
    - Implement get_policy with fallback to default policy
    - Implement apply_policy: filter memories by store rules (allowed types), discard by ignore patterns, apply priority weight overrides
    - Default policy: extract all supported memory_types
    - Create `contexta/core/policy/templates.py` with built-in templates: coding-agent, crm-agent, tutor-agent
    - Support extending built-in templates with custom store/ignore rules
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 18.7, 18.8_

  - [ ]* 10.2 Write property tests for policy engine (Properties 32, 33, 34, 35)
    - **Property 32: Policy store/ignore rule enforcement**
    - Verify extraction only produces memories of allowed types and discards content matching ignore patterns
    - **Property 33: Policy priority weight override**
    - Verify custom priority weights override default base scores for specified types
    - **Property 34: Policy registration round-trip**
    - Verify register then get returns equivalent policy definition
    - **Property 35: Policy template extension**
    - Verify extended templates contain both base and custom rules
    - Use Hypothesis: random memory types, random content patterns, random policy definitions
    - **Validates: Requirements 18.1, 18.3, 18.4, 18.5, 18.8**

  - [x] 10.3 Implement schema registry
    - Create `contexta/core/schema_registry/registry.py` with SchemaRegistry class
    - Implement register: validate schema (no duplicate fields, valid types, required fields specified), store tenant-scoped
    - Support field types: string, number, boolean, date, enum, array, nested object
    - Implement extract_with_schema: extract data into schema-defined fields, validate against constraints
    - On validation failure: store memory with raw content (structured_data=null), flag for review
    - Include schema name and field mapping in explain response for schema-typed memories
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.7, 19.8_

  - [ ]* 10.4 Write property tests for schema registry (Properties 36, 37)
    - **Property 36: Schema registration round-trip**
    - Verify valid schemas can be registered and retrieved equivalently; invalid schemas (duplicate fields, invalid types) are rejected
    - **Property 37: Schema validation failure handling**
    - Verify extracted data failing validation results in raw content storage with flag for review
    - Use Hypothesis: custom schema strategies with random field definitions
    - **Validates: Requirements 19.1, 19.2, 19.4, 19.5**

- [ ] 11. Hybrid retrieval engine
  - [x] 11.1 Implement retrieval engine core
    - Create `contexta/core/retrieval/engine.py` with RetrievalEngine class
    - Implement semantic_search using pgvector cosine similarity
    - Implement keyword_search using PostgreSQL full-text search on title, content, tags
    - Implement graph_expand with BFS through entity graph within configurable hop depth
    - Implement weighted combination: 40% semantic + 25% graph + 20% importance + 10% recency + 5% keyword
    - Implement LLM-based reranking for final ordering (with graceful fallback if LLM unavailable)
    - Enforce tenant isolation on all searches (organization_id + user_id)
    - Apply cold state ranking penalty of 0.3; exclude archived memories unless explicitly requested
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ]* 11.2 Write property tests for retrieval (Properties 17, 18, 19, 30)
    - **Property 17: Retrieval weighted score computation**
    - Verify combined score = 0.40*semantic + 0.25*graph + 0.20*importance + 0.10*recency + 0.05*keyword
    - **Property 18: Graph expansion depth bound**
    - Verify all returned entities are reachable within N hops from query entity
    - **Property 19: Context excludes archived and invalidated memories**
    - Verify no memory with is_archived=true or valid_to set appears in results
    - **Property 30: Cold memory ranking penalty**
    - Verify cold state memories have relevance reduced by 0.3
    - Use Hypothesis: `st.floats(0, 1)` for component scores, random graph structures, random memory states
    - **Validates: Requirements 8.3, 8.4, 9.4, 12.3, 20.7, 20.8**

  - [x] 11.3 Implement retrieval feedback engine
    - Create `contexta/core/retrieval/feedback.py` with RetrievalFeedbackEngine class
    - Implement record_retrieval: track which memories were retrieved per context request
    - Implement record_usage: record positive (used) or negative (ignored) signals
    - Implement compute_utility_ratio: usage_count / retrieval_count
    - Implement apply_importance_adjustments: reduce importance by 0.1 for 10+ ignored with zero positive; increase by 0.05 for usage ratio > 0.8 over 10+ retrievals
    - Store feedback in retrieval_feedback table scoped to org_id and user_id
    - _Requirements: 22.1, 22.2, 22.3, 22.4, 22.5, 22.6, 22.7, 22.8_

  - [ ]* 11.4 Write property tests for retrieval feedback (Property 38)
    - **Property 38: Retrieval feedback importance adjustments**
    - Verify 10+ ignored signals with zero positive → importance reduced by 0.1
    - Verify usage ratio > 0.8 over 10+ retrievals → importance increased by 0.05
    - Use Hypothesis: `st.integers(min_value=0)` for signal counts, `st.floats(0, 1)` for ratios
    - **Validates: Requirements 22.5, 22.6**

- [ ] 12. Context builder and planner
  - [x] 12.1 Implement context planner
    - Create `contexta/core/context/planner.py` with ContextPlanner class
    - Implement default weight allocation: projects=35%, goals=20%, facts=15%, episodic=15%, preferences=10%, relationships=5%
    - Support custom weight overrides from developer configuration
    - Fill each category with highest-relevance memories within budget
    - Redistribute unused tokens proportionally to other categories
    - Prefer CompressedSummaries over raw memories when available
    - Allocate SemanticClusters as units rather than splitting members
    - Include UserModel and ProjectSnapshots before individual memories
    - Report actual token usage per category in response metadata
    - _Requirements: 27.1, 27.2, 27.3, 27.4, 27.5, 27.6, 27.7, 27.8, 27.9_

  - [ ]* 12.2 Write property tests for context planner (Properties 48, 49, 50, 51)
    - **Property 48: Token budget allocation with default weights**
    - Verify allocation matches: projects=budget×0.35, goals=budget×0.20, facts=budget×0.15, episodic=budget×0.15, preferences=budget×0.10, relationships=budget×0.05
    - **Property 49: Token budget redistribution**
    - Verify unused tokens redistributed proportionally; total allocation equals original budget
    - **Property 50: Token budget custom weights override**
    - Verify custom weights replace defaults for allocation
    - **Property 51: Context planner reports actual usage**
    - Verify metadata contains per-category token counts summing to total used
    - Use Hypothesis: `st.integers(min_value=100)` for budgets, random category populations
    - **Validates: Requirements 27.2, 27.3, 27.5, 27.9**

  - [x] 12.3 Implement context builder
    - Create `contexta/core/context/builder.py` with ContextBuilder class
    - Assemble structured response: user_profile, active_projects, preferences, goals, recent_events, relevant_memories
    - Accept configuration: num_recent_messages, num_relevant_memories, graph_depth, withUserModel, token_budget
    - Delegate token allocation to ContextPlanner when budget specified
    - Filter out archived and invalidated memories
    - Order memories within sections by combined relevance score (descending)
    - Cache assembled context in Redis (Hot_Context) with session-scoped TTL
    - Return cached version when no new memories stored since cache creation
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [ ]* 12.4 Write property test for context ordering (Property 20)
    - **Property 20: Context section ordering**
    - Verify memories within each section are ordered by combined relevance score descending
    - Use Hypothesis: random lists of scored memories
    - **Validates: Requirements 9.5**

  - [x] 12.5 Implement retrieval and context API routes
    - Create `contexta/api/routes/retrieval.py` with POST /retrieve endpoint
    - Create `contexta/api/routes/memories.py` with GET /context endpoint
    - Wire retrieval engine and context builder into API layer
    - Enforce tenant isolation via middleware
    - _Requirements: 8.1, 9.1_

- [x] 13. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. Memory lifecycle management
  - [x] 14.1 Implement lifecycle operations API
    - Create lifecycle endpoints in `contexta/api/routes/memories.py`: pin, unpin, archive, restore, delete
    - Pin: set is_pinned=true, exclude from decay
    - Unpin: set is_pinned=false, re-enable decay
    - Archive: set is_archived=true, exclude from retrieval
    - Restore: set is_archived=false, re-include in retrieval
    - Delete: permanently remove memory_record, embeddings, graph edges, version history, cluster memberships, feedback
    - Enforce all operations scoped to authenticated user_id and organization_id
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [ ]* 14.2 Write property tests for lifecycle (Properties 25, 26, 27, 28)
    - **Property 25: Lifecycle operation round-trip**
    - Verify pin→unpin results in is_pinned=false; archive→restore results in is_archived=false
    - **Property 26: Delete removes all traces**
    - Verify deleted memory_id returns no results from any table
    - **Property 27: Lifecycle authorization**
    - Verify operations where actor org_id != memory org_id are rejected
    - **Property 28: Pinned memories immune to decay**
    - Verify is_pinned=true memories never have state transitioned by decay engine
    - Use Hypothesis: random memory states, random org_id pairs
    - **Validates: Requirements 7.6, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 20.6**

- [ ] 15. Decay engine
  - [x] 15.1 Implement decay engine
    - Create `contexta/core/decay/engine.py` with DecayEngine class
    - Implement state transitions: active→warm (30 days), warm→cold (90 days), cold→archived (180 days)
    - Implement reactivation: warm/cold memory accessed → transition back to active
    - Exclude pinned memories from all transitions
    - Run as periodic Celery Beat task (daily)
    - Create `contexta/workers/decay_tasks.py` with scheduled decay cycle task
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5, 20.6, 20.9_

  - [ ]* 15.2 Write property tests for decay (Property 29)
    - **Property 29: Decay state transitions by age**
    - Verify: active + 30 days no access → warm; warm + 90 days → cold; cold + 180 days → archived
    - Verify: warm/cold + access → active
    - Verify: pinned memories never transition
    - Use Hypothesis: random ages, random states, random is_pinned flags
    - **Validates: Requirements 20.2, 20.3, 20.4, 20.5**

- [ ] 16. Session management and explainability
  - [x] 16.1 Implement session management
    - Create `contexta/api/routes/sessions.py` with session endpoints
    - Create session record on initiation (session_id, user_id, org_id, start timestamp)
    - Store messages with session_id association
    - Trigger Epilogue_Worker on session end for full extraction
    - Cache active session data in Redis for low-latency access
    - Implement contexta.inspect(userId) returning session history with associated memories
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

  - [x] 16.2 Implement explainability API
    - Create explain endpoint in `contexta/api/routes/memories.py`
    - Return extraction source (session_id, triggering message content)
    - Return classification reasoning (why memory_type was assigned)
    - Return scoring breakdown (importance, confidence, freshness, utility with explanations)
    - Include supersession history for superseded memories (previous values, timestamps)
    - Implement contexta.timeline(userId) returning chronological memory events
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ]* 16.3 Write property tests for explainability (Properties 23, 24)
    - **Property 23: Timeline chronological ordering**
    - Verify timeline events are ordered by timestamp ascending
    - **Property 24: Explain completeness for superseded memories**
    - Verify superseded memories include non-empty supersession history with previous values and timestamps
    - Use Hypothesis: random lists of timestamped events, random supersession chains
    - **Validates: Requirements 11.4, 11.5**

- [ ] 17. Audit logging
  - [x] 17.1 Implement audit logging
    - Create `contexta/repositories/audit_repo.py` with audit log persistence
    - Log all significant operations: memory create, update, delete, pin, unpin, archive, restore, supersession, retrieval queries, reflection actions, dream cycle evaluations
    - Each entry: operation_type, actor_id, timestamp, target_id, details (JSON)
    - Scope audit log access to authenticated organization_id
    - Retain logs for minimum 90 days
    - Integrate audit logging into all existing components (memory repo, lifecycle, retrieval, truth maintenance)
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_

  - [ ]* 17.2 Write property test for audit trail (Property 31)
    - **Property 31: Audit trail completeness**
    - Verify every significant operation produces an audit log entry with operation_type, actor, timestamp, and target_id
    - Use Hypothesis: random operations, verify corresponding audit entries exist
    - **Validates: Requirements 16.1, 16.2, 16.3, 21.11, 26.10**

- [x] 18. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 19. Memory compression engine
  - [x] 19.1 Implement memory compression engine
    - Create `contexta/core/compression/engine.py` with MemoryCompressionEngine class
    - Generate CompressedSummary when entity has 20+ associated memories
    - Summary contains: entity_id, summary_text, key_facts, confidence, source_memory_count, generated_at
    - Mark summary as stale when new memories added to entity
    - Regenerate stale summaries incorporating new memories
    - Preserve links to source memories for drill-down
    - Achieve minimum 60% token reduction vs delivering all source memories
    - _Requirements: 24.1, 24.2, 24.3, 24.4, 24.5, 24.6, 24.7, 24.8_

  - [ ]* 19.2 Write property tests for compression (Properties 41, 42, 43, 44)
    - **Property 41: Compressed summary field completeness**
    - Verify entity_id, summary_text, key_facts, confidence, source_memory_count, generated_at are all non-null; source_memory_count >= 20
    - **Property 42: Compressed summary staleness on new memory**
    - Verify adding a new memory to entity with existing summary sets is_stale=true
    - **Property 43: Compressed summary token reduction**
    - Verify summary token count <= 40% of combined source memory tokens
    - **Property 44: Context prefers compressed summaries**
    - Verify Context_Builder includes non-stale summary rather than raw memories
    - Use Hypothesis: random memory collections of varying sizes, random token counts
    - **Validates: Requirements 24.1, 24.2, 24.3, 24.4, 24.8**

- [ ] 20. Semantic cluster engine
  - [x] 20.1 Implement semantic cluster engine
    - Create `contexta/core/clustering/engine.py` with SemanticClusterEngine class
    - Identify groups of 3+ related memories/entities via embedding proximity + graph relationships
    - Assign LLM-generated descriptive names to clusters
    - Add semantically related new memories to existing clusters
    - Remove invalidated/archived memories from clusters; dissolve cluster if < 3 members
    - Update clusters during Reflection Engine cycles and on high-importance memory storage
    - Scope clusters to user_id and organization_id
    - _Requirements: 25.1, 25.2, 25.3, 25.4, 25.5, 25.6, 25.7, 25.8_

  - [ ]* 20.2 Write property test for semantic clusters (Property 45)
    - **Property 45: Semantic cluster minimum membership**
    - Verify cluster member count >= 3; removing a member below 3 dissolves the cluster
    - Use Hypothesis: random cluster sizes, random removal operations
    - **Validates: Requirements 25.4, 25.6**

- [ ] 21. Reflection engine
  - [x] 21.1 Implement reflection engine
    - Create `contexta/core/reflection/engine.py` with ReflectionEngine class
    - Execute as periodic Celery Beat task (configurable, default nightly)
    - Implement duplicate merge: find 3+ memories with same fact → consolidate into one
    - Implement contradiction detection: trigger TruthMaintenanceEngine for missed contradictions
    - Implement dormant goal detection: goals not referenced in 180 days → mark dormant, reduce importance by 0.3
    - Generate ProjectSnapshots for active project entities (technologies, status, tasks, relationships)
    - Generate UserModels (languages, projects, preferences, goals, skills)
    - Invoke MemoryCompressionEngine for entities with 20+ memories
    - Invoke SemanticClusterEngine to identify/update clusters
    - Log all maintenance actions in audit trail
    - Create `contexta/workers/reflection_tasks.py` with scheduled task
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 21.7, 21.8, 21.9, 21.10, 21.11_

  - [ ]* 21.2 Write property tests for reflection (Properties 46, 47)
    - **Property 46: Dormant goal detection**
    - Verify goal-type memories not referenced for 180+ days are marked dormant with importance reduced by 0.3
    - **Property 47: Reflection duplicate merge**
    - Verify 3+ memories with same fact → only one consolidated memory remains after reflection
    - Use Hypothesis: random goal memories with varying last-referenced dates, random duplicate memory sets
    - **Validates: Requirements 21.2, 21.4**

- [ ] 22. Dream cycle engine
  - [x] 22.1 Implement dream cycle engine
    - Create `contexta/core/dream/engine.py` with DreamCycleEngine class
    - Execute as periodic Celery Beat task (configurable, default weekly)
    - Generate synthetic questions based on known entities and relationships
    - Attempt retrieval using RetrievalEngine for each question
    - Evaluate answer accuracy, completeness, consistency
    - On retrieval failure/low confidence: create MissingMemoryCandidate with question and related entity
    - On retrieval success: increment utility scores of contributing memories
    - On retrieval failure: decrement utility scores of retrieved-but-unhelpful memories
    - Generate compressed summaries for entities with high retrieval quality but inefficient delivery
    - Log all evaluation results in audit trail
    - Create `contexta/workers/dream_tasks.py` with scheduled task
    - _Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7, 26.8, 26.9, 26.10_

  - [ ]* 22.2 Write property test for dream cycle (Property 52)
    - **Property 52: Dream cycle gap identification**
    - Verify failed/low-confidence retrieval during dream evaluation creates MissingMemoryCandidate with question text and related entity reference
    - Use Hypothesis: random entity sets, mock retrieval results with varying confidence
    - **Validates: Requirements 26.5, 26.6**

- [x] 23. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 24. API middleware, auth, and integration wiring
  - [x] 24.1 Implement authentication and tenant middleware
    - Create `contexta/api/middleware/auth.py` with authentication middleware
    - Create `contexta/api/middleware/tenant.py` with tenant context extraction
    - Validate authenticated tenant matches organization_id on every request
    - Reject cross-tenant access with 403 authorization error
    - Wire middleware into FastAPI application
    - _Requirements: 14.3, 14.4_

  - [x] 24.2 Wire full extraction pipeline (observation → storage)
    - Connect observation ingestion → Celery task → extraction worker → sensitive scan → deduplication → entity resolution → truth maintenance → scoring → storage → embedding generation
    - Ensure each step chains to the next via Celery task chaining
    - Implement error handling: retry with exponential backoff, dead letter queue for persistent failures
    - _Requirements: 1.2, 2.5, All pipeline requirements_

  - [x] 24.3 Implement Celery Beat scheduler for periodic tasks
    - Configure Celery Beat with schedules: decay (daily), reflection (nightly), dream cycle (weekly)
    - Wire decay_tasks, reflection_tasks, dream_tasks into beat schedule
    - Ensure periodic tasks are tenant-aware (iterate all active tenants)
    - _Requirements: 20.9, 21.1, 26.1_

- [ ] 25. Integration tests
  - [ ]* 25.1 Write integration tests for full pipeline
    - Test observation → extraction → dedup → entity resolution → truth maintenance → scoring → storage → embedding
    - Test retrieval: semantic + keyword + graph combined results
    - Test context building with cache hit/miss scenarios
    - Test multi-tenancy: verify cross-tenant isolation end-to-end
    - Test Redis caching: Hot_Context behavior
    - Test embedding pipeline: async generation and pgvector storage
    - Use PostgreSQL test container with pgvector and Redis test container
    - _Requirements: All pipeline requirements_

  - [ ]* 25.2 Write integration tests for background workers
    - Test reflection cycle: duplicate merge, snapshot generation, user model synthesis
    - Test decay cycle: state transitions across full lifecycle
    - Test dream cycle: question generation, retrieval evaluation, gap identification
    - Test Celery task chaining and error recovery
    - _Requirements: 20.1-20.9, 21.1-21.11, 26.1-26.10_

- [x] 26. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at logical boundaries
- Property tests validate the 52 universal correctness properties defined in the design document
- Unit tests validate specific examples and edge cases
- Integration tests use PostgreSQL+pgvector and Redis test containers
- All code uses Python 3.11+, FastAPI, SQLAlchemy 2.0, Celery, Redis, and Hypothesis
- LLM calls are mocked in tests for deterministic behavior
- Embedding service is mocked with fixed-dimension random vectors for similarity testing

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "1.4"] },
    { "id": 3, "tasks": ["1.5", "2.1", "2.3"] },
    { "id": 4, "tasks": ["2.2", "2.4", "2.5"] },
    { "id": 5, "tasks": ["4.1", "5.1", "5.3"] },
    { "id": 6, "tasks": ["4.2", "4.3", "5.2", "5.4", "6.1"] },
    { "id": 7, "tasks": ["4.4", "6.2", "7.1"] },
    { "id": 8, "tasks": ["7.2", "7.3"] },
    { "id": 9, "tasks": ["7.4", "9.1", "9.2"] },
    { "id": 10, "tasks": ["10.1", "10.3"] },
    { "id": 11, "tasks": ["10.2", "10.4", "11.1"] },
    { "id": 12, "tasks": ["11.2", "11.3"] },
    { "id": 13, "tasks": ["11.4", "12.1"] },
    { "id": 14, "tasks": ["12.2", "12.3"] },
    { "id": 15, "tasks": ["12.4", "12.5", "14.1"] },
    { "id": 16, "tasks": ["14.2", "15.1", "16.1", "16.2"] },
    { "id": 17, "tasks": ["15.2", "16.3", "17.1"] },
    { "id": 18, "tasks": ["17.2", "19.1"] },
    { "id": 19, "tasks": ["19.2", "20.1"] },
    { "id": 20, "tasks": ["20.2", "21.1"] },
    { "id": 21, "tasks": ["21.2", "22.1"] },
    { "id": 22, "tasks": ["22.2", "24.1", "24.2", "24.3"] },
    { "id": 23, "tasks": ["25.1", "25.2"] }
  ]
}
```
