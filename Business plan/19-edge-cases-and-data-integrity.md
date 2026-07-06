# 19 — Edge Cases and Data Integrity

This document is the catch-all for edge cases that don't fit neatly into other docs. Every item here is a real failure mode an agent dev will hit eventually. We address each one with a defined behavior, not a hand-wave.

The customer's request was *"add what I'm missing."* This document captures the full list.

## Categories

1. Duplicate writes and replay
2. Contradictory facts and supersession
3. Out-of-order events
4. Schema drift
5. Bad inputs
6. Quota and rate edges
7. Multi-user, multi-session edges
8. Compliance and deletion
9. Slow paths and performance edges
10. Cross-tenant edges
11. Recovery and backfill
12. Migration and version-bump edges


## 1. Duplicate writes and replay

| Case | Behavior |
|---|---|
| Same `Idempotency-Key` + same body | Return original response unchanged (24h window) |
| Same key + different body | 409 with `error.original_request_id` |
| Same key, original still in flight | 409 `IDEMPOTENCY_IN_FLIGHT` with `Retry-After: 5` |
| No key, retry of a successful write | New observation created (warned in docs to use keys) |
| Old idempotency key (>24h) reused | Treated as new write |

See [16-error-handling-and-failsafe.md](./16-error-handling-and-failsafe.md) for the storage contract.

## 2. Contradictory facts and supersession

The `TruthMaintenanceEngine` already exists in `contexta/core/truth/maintenance.py`. Behavior:

| Case | Behavior |
|---|---|
| New memory contradicts existing on same entity+type | Old memory's `valid_to` set; new memory linked via `SUPERSEDED_BY` edge; old preserved in `memory_version` |
| Multiple contradictions in one batch | Resolved in extraction order; final memory wins |
| Contradictions across user_ids (rare) | Ignored — each user has their own truth |
| Soft contradiction (similar but not exclusive) | Both kept; surfaced in `explain()` as `related` |
| Memory contradicts a pinned memory | Pinned memory takes precedence; new memory stored as `pending_review` flag (audit log + dashboard surfaces it) |

The `explain(memory_id)` response includes the full supersession history for any memory chain.

## 3. Out-of-order events

Agents may submit observations out of chronological order (e.g., backfilling history).

| Case | Behavior |
|---|---|
| Observation timestamp earlier than current time | Accepted; `valid_from` set to observation timestamp, `created_at` to receive time |
| Two observations submitted out of order, both extract the same entity | Truth maintenance respects `valid_from`; older fact gets `valid_to`-supersession by newer |
| Future-dated observation | Rejected with 422 (timestamp > now+1 hour) |
| Same session, message timestamps reversed | Accepted; we sort by message timestamp before extraction prompt |

## 4. Schema drift

The customer's registered schema may not match what the LLM extracts.

| Case | Behavior |
|---|---|
| Extraction produces a field not in schema | Field dropped, warning in explain output |
| Extraction missing a required field | Retry with reprompt up to 3 times; on final failure store memory with `structured_data=null`, flag for review |
| Schema field type mismatch (string but extracted number) | Coerce when safe (number → string); reject when unsafe; flag for review |
| Schema renamed mid-stream | Old schema version still applies to existing memories; new version applies to new |
| Schema deleted | Memories using it stay; mark schema `deprecated`; new extraction falls back to default |

Memories flagged for review are visible in dashboard at `/dashboard/memories?flag=schema_validation_failed`.

## 5. Bad inputs

| Case | Behavior |
|---|---|
| Body > 1 MB | 422 `PAYLOAD_TOO_LARGE` |
| Batch > 50 observations | 422 `BATCH_TOO_LARGE` |
| Malformed JSON | 422 `INVALID_JSON` |
| Missing required field | 422 `MISSING_FIELD` with field name |
| `user_id` not a UUID | 422 `INVALID_USER_ID` |
| `user_id` is a UUID but never seen | Accepted; we don't authenticate end-users |
| `messages` empty array | 422 `EMPTY_MESSAGES` |
| `messages[i].role` not in {user, assistant, system, tool} | 422 with index |
| `messages[i].content` empty | Allowed but a warning is in explain output |
| `metadata` > 4 KB | 422 `METADATA_TOO_LARGE` |
| Non-UTF-8 in any string field | 422 `INVALID_ENCODING` |
| Extremely long single message (> 100 KB) | Truncated to 100 KB before extraction; warning in explain |
| `policy` references unregistered policy | 404 `POLICY_NOT_FOUND` |

## 6. Quota and rate edges

| Case | Behavior |
|---|---|
| Soft cap, observation submitted at 99% | Accepted, header `X-contexta-Quota-Used: 0.99`, dashboard banner |
| Soft cap, at 100.01% | Accepted, overage starts; email at 100% threshold (one time per period) |
| Hard cap engaged | 429 `QUOTA_EXCEEDED` with `Retry-After` to period rollover |
| Rate limited | 429 `RATE_LIMITED` with `Retry-After` (seconds) |
| Cap toggled hard mid-period | New writes start returning 429 immediately if already over |
| Plan downgrade reduces limits below current usage | Grandfather until next period boundary; warn in dashboard |
| Quota exceeded during retry burst | Retries respect `Retry-After`; SDK auto-backs off |

## 7. Multi-user, multi-session edges

| Case | Behavior |
|---|---|
| Same user_id across multiple sessions | All memories tagged with originating session_id; retrieval can filter or merge |
| Multiple users in one session (group chat) | Customer should pass `user_id` for the primary user; we do not auto-attribute |
| Session never explicitly ended | Auto-archived after 30 days of no activity; epilogue worker fires |
| Session ended twice | Idempotent: second call returns same response |
| Session has 100k+ messages | Allowed; extraction batches messages 100 at a time |
| user_id deleted from customer's system but memories remain | Memories remain; customer can call `DELETE /v1/users/{user_id}/memories` to purge |

## 8. Compliance and deletion

| Case | Behavior |
|---|---|
| Customer requests "delete all my data" | Soft delete within 1 hour; hard delete within 30 days; export emailed |
| Customer requests "delete user X's data" | DELETE /v1/users/{user_id}/memories; cascades to embeddings, edges, versions, cluster memberships, feedback |
| Tenant deletion mid-period | Period closed pro-rata; final invoice generated |
| EU resident requests data export (GDPR) | Self-serve in dashboard; JSONL signed URL valid 24h |
| Audit log retention vs deletion conflict | Audit log retained per legal hold (7 years for billing) even after tenant delete |
| Backup containing deleted data | Backups expire on 30-day retention; deletion is eventually consistent across backups |

## 9. Slow paths and performance edges

| Case | Behavior |
|---|---|
| Extraction queue depth > 10k for one tenant | That tenant's queue de-prioritized; observations still accepted (202) |
| Retrieval p99 > 500ms | Auto-alert; investigation; replica may need failover or index rebuild |
| Embedding service down | Memory stored without embedding; retrieval works on keyword + graph + importance only; embedding generated on next retry |
| LLM rerank timeout | Fall back to non-reranked ordering; log warning; do NOT bill the rerank |
| HNSW index corruption | Rebuild from scratch (~30 min on 1M memories); during rebuild, retrieval falls back to brute-force scan with extended latency |

## 10. Cross-tenant edges

| Case | Behavior |
|---|---|
| Customer A queries tenant B's data via tampered org_id | 403 (gateway enforces tenant from JWT, not body) |
| Operator queries customer data | Logged in audit + customer-visible; requires ticket |
| Internal smoke tests against production | Use dedicated tenant `internal-test`; never billed; isolated from customer data |
| Customer accidentally uses test API key in production | Test keys (mk_test_*) refuse to write live data; 403 on production endpoints with informative error |

## 11. Recovery and backfill

| Case | Behavior |
|---|---|
| Customer wants to import historical conversations | `POST /v1/observations/batch` repeatedly; same idempotency keys safe to replay |
| Postgres restored from backup older than 5 min | Replay WAL up to incident time; observations after that point are in the Redis Stream durable buffer; replay |
| Customer wants to "rebuild memories from raw" | Re-run extraction on stored observations; existing memories deduped or superseded by truth maintenance |
| Disaster: regional failover to HEL1 | RTO 15-30 min; in-flight observations preserved in Redis Stream; replay on new primary |

## 12. Migration and version-bump edges

| Case | Behavior |
|---|---|
| API v1 → v2 transition | Both versions supported for 12 months; SDK 1.x → v1, SDK 2.x → v2; migration guide published |
| Deprecated field removal | Announced 90 days before, dashboard banner, email; fields return null after deprecation; removed in next major |
| Schema model change (Memory adds new column) | Default value applied to existing rows; SDK ignores unknown columns gracefully |
| Pricing model change | Existing customers grandfathered 12 months; new customers see new pricing immediately |

## What we explicitly accept as edge cases without first-class support

- **Real-time bidirectional streaming.** No WebSocket retrieval. Customers poll or use webhooks.
- **GraphQL.** REST only at v1.
- **Custom LLM models hosted by customer.** BYOK supports OpenAI, Anthropic, Google. Self-hosted models (Llama, Mistral) require Enterprise tier.
- **Image / audio / video memories.** Text only at v1. Multimodal post-launch.
- **Sub-tenant isolation.** Tenant = organization. We don't model "customer's customer" hierarchy. Their workaround is project-per-end-customer.
- **Time-travel queries (point-in-time view of memory).** `valid_to` enables this in principle, but we don't expose a public time-travel API.
- **Bulk admin operations.** Operators can run scripts but customers can't bulk-edit beyond what the lifecycle endpoints provide.

## Acceptance criteria for "we handle this case"

For every edge case in this doc, we commit to:

1. A defined behavior (above).
2. A test case in CI (where mechanically possible).
3. An audit log entry (when the case affects customer data).
4. A line in the public docs (when the customer needs to know).
5. A monitoring metric (when the case is operationally interesting).

If any of those four are missing for a case, we have a gap. Quarterly review of this doc ensures coverage.
