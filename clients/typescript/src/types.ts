export interface contextaConfig {
  apiKey: string;
  baseUrl?: string;
  timeout?: number;
  maxRetries?: number;
  telemetry?: boolean;
}

export interface ObserveInput {
  userId: string;
  organizationId: string;
  sessionId: string;
  messages: Record<string, unknown>[];
  metadata?: Record<string, unknown>;
  policy?: string;
}

export interface RetrieveInput {
  userId: string;
  organizationId: string;
  queryText: string;
  memoryTypes?: string[];
  tags?: string[];
  limit?: number;
  graphDepth?: number;
  includeCold?: boolean;
  includeArchived?: boolean;
}

export interface ContextInput {
  userId: string;
  organizationId: string;
  sessionId: string;
  tokenBudget?: number;
  includeUserModel?: boolean;
  numRecentMessages?: number;
  numRelevantMemories?: number;
  graphDepth?: number;
}

export interface ObserveResponse {
  jobId: string;
  status: string;
}

export interface BatchObserveResponse {
  jobs: ObserveResponse[];
  status: string;
}

export interface ScoredMemory {
  memory: Memory;
  score: number;
  semanticScore: number;
  graphScore: number;
  importanceScore: number;
  recencyScore: number;
  keywordScore: number;
}

export interface ScoreBreakdown {
  confidence: number;
  importance: number;
  utilityScore: number;
}

export interface Context {
  userProfile: UserProfile | null;
  activeProjects: Project[];
  preferences: Preference[];
  goals: Goal[];
  recentEvents: Event[];
  relevantMemories: ScoredMemory[];
  tokenUsage: TokenUsage;
  cacheHit: boolean;
  requestId: string;
}

export interface TokenUsage {
  total: number;
  bySection: Record<string, number>;
}

export interface ContextSection {
  title: string;
  content: string;
  tokenCount: number;
}

export interface Memory {
  id: string;
  userId: string;
  organizationId: string;
  memoryType: string;
  title: string;
  content: string;
  structuredData: Record<string, unknown> | null;
  sourceType: string;
  confidence: number;
  importance: number;
  utilityScore: number;
  tags: string[] | null;
  sessionId: string | null;
  memoryState: string;
  isPinned: boolean;
  isArchived: boolean;
  validFrom: string | null;
  validTo: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  lastAccessedAt: string | null;
}

export interface Explanation {
  memoryId: string;
  source: {
    sourceType: string;
    sessionId: string | null;
  };
  classification: {
    memoryType: string;
    tags: string[];
  };
  scoring: ScoreBreakdown;
  supersessionHistory: SupersessionEntry[];
}

export interface SupersessionEntry {
  id: string;
  content: string;
  importance: number;
  validFrom: string | null;
  validTo: string | null;
  supersededById: string | null;
}

export interface TimelineEvent {
  id: string;
  eventType: "created" | "archived" | "superseded";
  timestamp: string | null;
  memory: {
    title: string;
    content: string;
    memoryType: string;
    isPinned: boolean;
    isArchived: boolean;
    memoryState: string;
  };
}

export interface Policy {
  id?: string;
  name: string;
  description?: string;
  rules: PolicyRule[];
  createdAt?: string;
  updatedAt?: string;
}

export interface PolicyRule {
  field: string;
  operator: string;
  value: unknown;
  action?: string;
}

export interface PolicyInput {
  name: string;
  description?: string;
  rules: PolicyRule[];
}

export interface Schema {
  id?: string;
  name: string;
  fields: FieldDef[];
  createdAt?: string;
  updatedAt?: string;
}

export interface FieldDef {
  name: string;
  type: "string" | "number" | "boolean" | "object" | "array" | "date";
  description?: string;
  required?: boolean;
  enum?: string[];
  default?: unknown;
}

export interface SchemaInput {
  name: string;
  fields: FieldDef[];
}

export interface Session {
  sessionId: string;
  userId: string;
  organizationId: string;
  startedAt: string;
  endedAt?: string | null;
  metadata?: Record<string, unknown> | null;
  memoryCount?: number;
  earliestMemoryCreatedAt?: string | null;
}

export interface UserProfile {
  userId: string;
  name?: string;
  traits?: Record<string, unknown>;
  summary?: string;
}

export interface Project {
  id: string;
  name: string;
  description?: string;
  status?: string;
  goals?: string[];
}

export interface Goal {
  id: string;
  description: string;
  progress?: number;
  status?: string;
  deadline?: string;
}

export interface Preference {
  id: string;
  key: string;
  value: unknown;
  category?: string;
}

export interface Event {
  id: string;
  type: string;
  description: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

export class contextaError extends Error {
  public status: number;
  public code: string;

  constructor(message: string, status: number, code: string) {
    super(message);
    this.name = "contextaError";
    this.status = status;
    this.code = code;
  }
}

export class AuthenticationError extends contextaError {
  constructor(message = "Authentication failed") {
    super(message, 401, "authentication_error");
    this.name = "AuthenticationError";
  }
}

export class AuthorizationError extends contextaError {
  constructor(message = "Not authorized") {
    super(message, 403, "authorization_error");
    this.name = "AuthorizationError";
  }
}

export class ValidationError extends contextaError {
  public errors: Record<string, string[]> | undefined;

  constructor(message = "Validation failed", errors?: Record<string, string[]>) {
    super(message, 422, "validation_error");
    this.name = "ValidationError";
    this.errors = errors;
  }
}

export class QuotaExceeded extends contextaError {
  constructor(message = "Quota exceeded") {
    super(message, 429, "quota_exceeded");
    this.name = "QuotaExceeded";
  }
}

export class RateLimited extends contextaError {
  public retryAfter: number | undefined;

  constructor(message = "Rate limited", retryAfter?: number) {
    super(message, 429, "rate_limited");
    this.name = "RateLimited";
    this.retryAfter = retryAfter;
  }
}

export class ServerError extends contextaError {
  constructor(message = "Internal server error", status = 500) {
    super(message, status, "server_error");
    this.name = "ServerError";
  }
}

export class NotFoundError extends contextaError {
  constructor(message = "Resource not found") {
    super(message, 404, "not_found");
    this.name = "NotFoundError";
  }
}

export class ConflictError extends contextaError {
  constructor(message = "Resource conflict") {
    super(message, 409, "conflict");
    this.name = "ConflictError";
  }
}

export interface MemoryListEntry {
  id: string;
  title: string;
  memoryType: string;
  memoryState: string;
  importance: number;
  confidence: number;
  tags: string[] | null;
  isPinned: boolean;
  isArchived: boolean;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface TimelineResponse {
  userId: string;
  events: TimelineEvent[];
}

export interface RetrieveResponse {
  status: string;
  query: string;
  results: ScoredMemory[];
}
