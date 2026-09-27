import { HttpClient, configFromEnv } from "./http.js";
import { ContextResult } from "./context.js";
import type {
  contextaConfig,
  AddRuleInput,
  BatchRetrievalEntry,
  BatchObserveResponse,
  ContextInput,
  Context,
  CreateSessionInput,
  DeleteResult,
  EndSessionResult,
  Explanation,
  FeedbackInput,
  FeedbackResult,
  HybridSearchInput,
  HybridSearchResponse,
  InvestigateInput,
  InvestigateResult,
  ListMemoriesInput,
  Memory,
  MemoryBatchEntry,
  MemoryBatchResponse,
  MemoryFlag,
  MemoryListEntry,
  ObserveInput,
  ObserveResponse,
  Policy,
  PolicyInput,
  ReflectInput,
  ReflectResult,
  RetrieveInput,
  RetrieveResponse,
  Schema,
  SchemaInput,
  SearchInput,
  Session,
  TimelineResponse,
  TraverseInput,
  TraverseResult,
  VectorSearchResponse,
} from "./types.js";

const DEPRECATION_WARNINGS = new Set<string>();

function warnDeprecated(oldName: string, newName: string): void {
  if (DEPRECATION_WARNINGS.has(oldName)) return;
  DEPRECATION_WARNINGS.add(oldName);
  console.warn(
    `[contexta] ${oldName} is deprecated and will be removed in a future major release; use ${newName} instead.`
  );
}

export class AsyncContexta {
  protected http: HttpClient;
  readonly organizationId?: string;

  constructor(config: contextaConfig) {
    this.http = new HttpClient(config);
    this.organizationId = config.organizationId;
  }

  static fromEnv(): AsyncContexta {
    return new AsyncContexta(configFromEnv());
  }

  async observe(input: ObserveInput): Promise<ObserveResponse> {
    return this.http.request<ObserveResponse>("POST", "/observations", {
      user_id: input.userId,
      organization_id: input.organizationId,
      session_id: input.sessionId,
      messages: input.messages,
      ...(input.metadata !== undefined && { metadata: input.metadata }),
      ...(input.policy !== undefined && { policy: input.policy }),
      ...(input.occurredAt !== undefined && { occurred_at: input.occurredAt }),
      ...(input.observedAt !== undefined && { observed_at: input.observedAt }),
      ...(input.sourceId !== undefined && { source_id: input.sourceId }),
      ...(input.messageId !== undefined && { message_id: input.messageId }),
      ...(input.timezone !== undefined && { timezone: input.timezone }),
    });
  }

  async observeBatch(inputs: ObserveInput[]): Promise<BatchObserveResponse> {
    const body = inputs.map((i) => ({
      user_id: i.userId,
      organization_id: i.organizationId,
      session_id: i.sessionId,
      messages: i.messages,
      ...(i.metadata !== undefined && { metadata: i.metadata }),
      ...(i.policy !== undefined && { policy: i.policy }),
      ...(i.occurredAt !== undefined && { occurred_at: i.occurredAt }),
      ...(i.observedAt !== undefined && { observed_at: i.observedAt }),
      ...(i.sourceId !== undefined && { source_id: i.sourceId }),
      ...(i.messageId !== undefined && { message_id: i.messageId }),
      ...(i.timezone !== undefined && { timezone: i.timezone }),
    }));
    return this.http.request<BatchObserveResponse>("POST", "/observations/batch", body);
  }

  async retrieve(input: RetrieveInput): Promise<RetrieveResponse> {
    return this.http.request<RetrieveResponse>("POST", "/retrieve", {
      user_id: input.userId,
      organization_id: input.organizationId,
      query_text: input.queryText,
      ...(input.memoryTypes !== undefined && { memory_types: input.memoryTypes }),
      ...(input.tags !== undefined && { tags: input.tags }),
      ...(input.limit !== undefined && { limit: input.limit }),
      ...(input.graphDepth !== undefined && { graph_depth: input.graphDepth }),
      ...(input.includeCold !== undefined && { include_cold: input.includeCold }),
      ...(input.includeArchived !== undefined && { include_archived: input.includeArchived }),
    });
  }

  async retrieveBatch(queries: RetrieveInput[]): Promise<BatchRetrievalEntry[]> {
    const res = await this.http.request<{ count: number; batchResults: BatchRetrievalEntry[] }>(
      "POST",
      "/retrieve/batch",
      {
        queries: queries.map((q) => ({
          user_id: q.userId,
          organization_id: q.organizationId,
          query_text: q.queryText,
          ...(q.memoryTypes !== undefined && { memory_types: q.memoryTypes }),
          ...(q.tags !== undefined && { tags: q.tags }),
          ...(q.limit !== undefined && { limit: q.limit }),
          ...(q.graphDepth !== undefined && { graph_depth: q.graphDepth }),
          ...(q.includeCold !== undefined && { include_cold: q.includeCold }),
          ...(q.includeArchived !== undefined && { include_archived: q.includeArchived }),
        })),
      }
    );
    return res.batchResults ?? [];
  }

  async search(input: SearchInput): Promise<VectorSearchResponse> {
    const params = new URLSearchParams({ query: input.query });
    if (input.userId) params.set("user_id", input.userId);
    if (input.limit !== undefined) params.set("limit", String(input.limit));
    if (input.threshold !== undefined) params.set("threshold", String(input.threshold));
    if (input.memoryType) params.set("memory_type", input.memoryType);

    return this.http.request("GET", `/memories/search?${params.toString()}`, undefined, {
      idempotent: true,
      headers: input.userId ? { "X-contexta-User-Id": input.userId } : undefined,
    });
  }

  async traverse(input: TraverseInput): Promise<TraverseResult> {
    const params = new URLSearchParams({ source: input.source });
    if (input.hops !== undefined) params.set("hops", String(input.hops));
    if (input.relationshipTypes && input.relationshipTypes.length > 0) {
      params.set("relationship_types", input.relationshipTypes.join(","));
    }
    if (input.direction) params.set("direction", input.direction);

    return this.http.request("GET", `/graph/traverse?${params.toString()}`, undefined, {
      idempotent: true,
    });
  }

  async hybrid(input: HybridSearchInput): Promise<HybridSearchResponse> {
    const params = new URLSearchParams({ query: input.query });
    if (input.userId) params.set("user_id", input.userId);
    if (input.limit !== undefined) params.set("limit", String(input.limit));
    if (input.maxHops !== undefined) params.set("max_hops", String(input.maxHops));
    if (input.vectorWeight !== undefined) params.set("vector_weight", String(input.vectorWeight));
    if (input.graphWeight !== undefined) params.set("graph_weight", String(input.graphWeight));
    if (input.includeCold !== undefined) params.set("include_cold", String(input.includeCold));

    return this.http.request("GET", `/memories/hybrid?${params.toString()}`, undefined, {
      idempotent: true,
      headers: input.userId ? { "X-contexta-User-Id": input.userId } : undefined,
    });
  }

  async context(input: ContextInput): Promise<ContextResult> {
    const params = new URLSearchParams();
    params.set("user_id", input.userId);
    params.set("organization_id", input.organizationId);
    params.set("session_id", input.sessionId);
    if (input.tokenBudget !== undefined) params.set("token_budget", String(input.tokenBudget));
    if (input.includeUserModel !== undefined) params.set("include_user_model", String(input.includeUserModel));
    if (input.numRecentMessages !== undefined) params.set("num_recent_messages", String(input.numRecentMessages));
    if (input.numRelevantMemories !== undefined) params.set("num_relevant_memories", String(input.numRelevantMemories));
    if (input.graphDepth !== undefined) params.set("graph_depth", String(input.graphDepth));

    const data = await this.http.request<Context>("GET", `/memories/context?${params.toString()}`, undefined, {
      idempotent: true,
      headers: { "X-contexta-User-Id": input.userId },
    });
    return new ContextResult(data);
  }

  async explain(memoryId: string): Promise<Explanation> {
    return this.http.request<Explanation>("GET", `/memories/${memoryId}/explain`, undefined, {
      idempotent: true,
    });
  }

  async pin(memoryId: string): Promise<MemoryFlag> {
    return this.http.request<MemoryFlag>("POST", `/memories/${memoryId}/pin`);
  }

  async unpin(memoryId: string): Promise<MemoryFlag> {
    return this.http.request<MemoryFlag>("POST", `/memories/${memoryId}/unpin`);
  }

  async archive(memoryId: string): Promise<MemoryFlag> {
    return this.http.request<MemoryFlag>("POST", `/memories/${memoryId}/archive`);
  }

  async restore(memoryId: string): Promise<MemoryFlag> {
    return this.http.request<MemoryFlag>("POST", `/memories/${memoryId}/restore`);
  }

  async delete(memoryId: string): Promise<DeleteResult> {
    return this.http.request<DeleteResult>("DELETE", `/memories/${memoryId}`);
  }

  async timeline(userId: string): Promise<TimelineResponse> {
    return this.http.request<TimelineResponse>("GET", `/memories/timeline/${userId}`, undefined, {
      idempotent: true,
    });
  }

  async getMemory(memoryId: string): Promise<Memory> {
    return this.http.request<Memory>("GET", `/memories/${memoryId}`, undefined, {
      idempotent: true,
    });
  }

  async listMemories(options?: ListMemoriesInput): Promise<MemoryListEntry[]> {
    const params = new URLSearchParams();
    if (options?.userId !== undefined) params.set("user_id", options.userId);
    if (options?.memoryType !== undefined) params.set("memory_type", options.memoryType);
    if (options?.state !== undefined) params.set("state", options.state);
    if (options?.pinned !== undefined) params.set("pinned", String(options.pinned));
    if (options?.archived !== undefined) params.set("archived", String(options.archived));
    if (options?.offset !== undefined) params.set("offset", String(options.offset));
    if (options?.limit !== undefined) params.set("limit", String(options.limit));

    return this.http.request<MemoryListEntry[]>("GET", `/memories?${params.toString()}`, undefined, {
      idempotent: true,
      headers: options?.userId ? { "X-contexta-User-Id": options.userId } : undefined,
    });
  }

  async listPolicies(): Promise<Policy[]> {
    return this.http.request<Policy[]>("GET", "/policies", undefined, { idempotent: true });
  }

  async registerPolicy(input: PolicyInput): Promise<Policy> {
    return this.http.request<Policy>("POST", "/policies", input as unknown as Record<string, unknown>);
  }

  async registerSchema(input: SchemaInput): Promise<Schema> {
    return this.http.request<Schema>("POST", "/schemas", input as unknown as Record<string, unknown>);
  }

  async ping(): Promise<{ status: string; version: string }> {
    return this.http.request<{ status: string; version: string }>("GET", "/healthz", undefined, {
      idempotent: true,
      absolute: true,
    });
  }

  async createSession(input: CreateSessionInput): Promise<Session> {
    return this.http.request<Session>("POST", "/sessions", {
      user_id: input.userId,
      organization_id: input.organizationId,
      metadata: input.metadata,
    });
  }

  async getSession(sessionId: string): Promise<Session> {
    return this.http.request<Session>("GET", `/sessions/${sessionId}`, undefined, {
      idempotent: true,
    });
  }

  async endSession(sessionId: string): Promise<EndSessionResult> {
    return this.http.request<EndSessionResult>("POST", `/sessions/${sessionId}/end`);
  }

  async getMany(memoryIds: string[]): Promise<MemoryBatchEntry[]> {
    const res = await this.http.request<MemoryBatchResponse>(
      "POST",
      "/memories/batch-get",
      { memory_ids: memoryIds }
    );
    return res.memories ?? [];
  }

  async feedback(memoryId: string, options: FeedbackInput): Promise<FeedbackResult> {
    return this.http.request<FeedbackResult>("POST", `/memories/${memoryId}/feedback`, {
      signal: options.signal,
      ...(options.userCorrection !== undefined && { user_correction: options.userCorrection }),
      penalty: options.penalty ?? 0.5,
    });
  }

  async addRule(options: AddRuleInput): Promise<ObserveResponse> {
    const tags = [...(options.tags ?? []), "rule", "procedural"];
    return this.observe({
      userId: options.userId,
      messages: [
        { role: "user", content: `Instruction / Operating Rule: ${options.rule}` },
        { role: "assistant", content: `Understood. I will strictly follow this rule: ${options.rule}` },
      ],
      metadata: { memory_type: "procedural", rule_title: options.title ?? "Behavioral Rule", tags },
    });
  }

  async investigate(options: InvestigateInput): Promise<InvestigateResult> {
    return this.http.request<InvestigateResult>("POST", "/retrieve/investigate", {
      query_text: options.queryText,
      user_id: options.userId,
      ...(options.organizationId !== undefined && { organization_id: options.organizationId }),
      max_hops: options.maxHops ?? 2,
      limit: options.limit ?? 15,
    });
  }

  async reflect(options: ReflectInput): Promise<ReflectResult> {
    return this.http.request<ReflectResult>("POST", "/memories/reflect", {
      user_id: options.userId,
      apply_supersession: options.applySupersession ?? true,
      min_occurrences_for_pattern: options.minOccurrencesForPattern ?? 3,
    });
  }

  /** Force the durable offline buffer to drain. Resolves to entries replayed. */
  async flush(): Promise<number> {
    return this.http.flush();
  }

  /** Release transport resources. Safe to call more than once. */
  close(): void {
    this.http.close();
  }
}

export class Contexta extends AsyncContexta {}

/** @deprecated Use {@link Contexta}. */
export class contexta extends Contexta {
  constructor(config: contextaConfig) {
    super(config);
    warnDeprecated("contexta", "Contexta");
  }

  static fromEnv(): contexta {
    warnDeprecated("contexta", "Contexta");
    return new contexta(configFromEnv());
  }
}

/** @deprecated Use {@link AsyncContexta}. */
export class Asynccontexta extends AsyncContexta {
  constructor(config: contextaConfig) {
    super(config);
    warnDeprecated("Asynccontexta", "AsyncContexta");
  }

  static fromEnv(): Asynccontexta {
    warnDeprecated("Asynccontexta", "AsyncContexta");
    return new Asynccontexta(configFromEnv());
  }
}

/**
 * Run `fn` with a client and always close it afterwards. The JavaScript equivalent
 * of Python's `with Contexta(...) as memory:` block.
 */
export async function withContexta<T>(
  config: contextaConfig,
  fn: (client: Contexta) => Promise<T>
): Promise<T> {
  const client = new Contexta(config);
  try {
    return await fn(client);
  } finally {
    client.close();
  }
}
