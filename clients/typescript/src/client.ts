import { HttpClient, configFromEnv } from "./http.js";
import { ContextResult } from "./context.js";
import type {
  contextaConfig,
  ObserveInput,
  ObserveResponse,
  BatchObserveResponse,
  RetrieveInput,
  RetrieveResponse,
  ContextInput,
  Context,
  Explanation,
  TimelineResponse,
  Memory,
  MemoryListEntry,
  Policy,
  PolicyInput,
  Schema,
  SchemaInput,
  Session,
} from "./types.js";

export class Asynccontexta {
  protected http: HttpClient;

  constructor(config: contextaConfig) {
    this.http = new HttpClient(config);
  }

  static fromEnv(): Asynccontexta {
    return new Asynccontexta(configFromEnv());
  }

  async observe(input: ObserveInput): Promise<ObserveResponse> {
    return this.http.request<ObserveResponse>("POST", "/observations", {
      user_id: input.userId,
      organization_id: input.organizationId,
      session_id: input.sessionId,
      messages: input.messages,
      ...(input.metadata !== undefined && { metadata: input.metadata }),
      ...(input.policy !== undefined && { policy: input.policy }),
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

  async search(input: {
    query: string;
    userId?: string;
    limit?: number;
    threshold?: number;
    memoryType?: string;
  }): Promise<{ mode: string; query: string; count: number; results: any[] }> {
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

  async traverse(input: {
    source: string;
    hops?: number;
    relationshipTypes?: string[];
    direction?: "both" | "outgoing" | "incoming";
  }): Promise<{ mode: string; root_entity: any; hops: number; nodes: any[]; edges: any[]; linked_memories: any[] }> {
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

  async hybrid(input: {
    query: string;
    userId?: string;
    limit?: number;
    maxHops?: number;
    vectorWeight?: number;
    graphWeight?: number;
    includeCold?: boolean;
  }): Promise<{ mode: string; query: string; count: number; results: any[] }> {
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
    });
    return new ContextResult(data);
  }

  async explain(memoryId: string): Promise<Explanation> {
    return this.http.request<Explanation>("GET", `/memories/${memoryId}/explain`, undefined, {
      idempotent: true,
    });
  }

  async pin(memoryId: string): Promise<{ memoryId: string; isPinned: boolean }> {
    return this.http.request<{ memoryId: string; isPinned: boolean }>("POST", `/memories/${memoryId}/pin`);
  }

  async unpin(memoryId: string): Promise<{ memoryId: string; isPinned: boolean }> {
    return this.http.request<{ memoryId: string; isPinned: boolean }>("POST", `/memories/${memoryId}/unpin`);
  }

  async archive(memoryId: string): Promise<{ memoryId: string; isArchived: boolean }> {
    return this.http.request<{ memoryId: string; isArchived: boolean }>("POST", `/memories/${memoryId}/archive`);
  }

  async restore(memoryId: string): Promise<{ memoryId: string; isArchived: boolean }> {
    return this.http.request<{ memoryId: string; isArchived: boolean }>("POST", `/memories/${memoryId}/restore`);
  }

  async delete(memoryId: string): Promise<{ memoryId: string; deleted: boolean }> {
    return this.http.request<{ memoryId: string; deleted: boolean }>("DELETE", `/memories/${memoryId}`);
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

  async listMemories(options?: {
    userId?: string;
    memoryType?: string;
    state?: string;
    pinned?: boolean;
    archived?: boolean;
    offset?: number;
    limit?: number;
  }): Promise<MemoryListEntry[]> {
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
    });
  }

  async createSession(input: {
    userId: string;
    organizationId: string;
    metadata?: Record<string, unknown>;
  }): Promise<Session> {
    return this.http.request<Session>("POST", "/sessions", {
      user_id: input.userId,
      organization_id: input.organizationId,
      metadata: input.metadata,
    });
  }

  async endSession(sessionId: string): Promise<{ sessionId: string; endedAt: string }> {
    return this.http.request<{ sessionId: string; endedAt: string }>("POST", `/sessions/${sessionId}/end`);
  }

  async getSession(sessionId: string): Promise<Session> {
    return this.http.request<Session>("GET", `/sessions/${sessionId}`, undefined, {
      idempotent: true,
    });
  }
}

export class contexta extends Asynccontexta {
  constructor(config: contextaConfig) {
    super(config);
  }

  static fromEnv(): contexta {
    return new contexta(configFromEnv());
  }
}
