import { auth } from "@/lib/auth";

const DEFAULT_CONTEXTA_API_URL = "http://localhost:8000";

function getcontextaApiUrl(): string {
  return (process.env.CONTEXTA_API_URL ?? DEFAULT_CONTEXTA_API_URL).replace(/\/$/, "");
}

async function getAuthHeaders(): Promise<Record<string, string>> {
  const session = await auth();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (session?.user) {
    headers["X-User-Id"] = session.user.id as string;
    headers["X-Org-Id"] = (session.user as any).org_id as string;
  }
  return headers;
}

async function requestcontexta<T>(path: string, init?: RequestInit): Promise<T> {
  const authHeaders = await getAuthHeaders();
  const response = await fetch(`${getcontextaApiUrl()}${path}`, {
    ...init,
    headers: {
      ...authHeaders,
      ...(init?.headers as Record<string, string> ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `contexta API returned ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export type MemorySummary = {
  id: string;
  title: string;
  memory_type: string;
  memory_state: string;
  importance: number;
  confidence: number;
  tags: string[] | null;
  is_pinned: boolean;
  is_archived: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type GraphNode = {
  id: string;
  name: string;
  entity_type: string;
  summary: string | null;
  memory_count: number;
};

export type GraphEdge = {
  source: string;
  target: string;
  relationship_type: string;
};

export type GraphResponse = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type ApiKey = {
  id: string;
  name: string;
  prefix: string;
  organization_id: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
};

export type CreatedApiKey = {
  token: string;
  key: ApiKey;
};

export async function listMemories(params?: {
  user_id?: string;
  memory_type?: string;
  state?: string;
  pinned?: boolean;
  archived?: boolean;
  offset?: number;
  limit?: number;
}): Promise<MemorySummary[]> {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) search.set(k, String(v));
    }
  }
  return requestcontexta<MemorySummary[]>(`/v1/memories?${search.toString()}`);
}

export async function getMemory(id: string): Promise<{
  id: string;
  title: string;
  content: string;
  memory_type: string;
  memory_state: string;
  importance: number;
  confidence: number;
  tags: string[] | null;
  source_type: string;
  structured_data: Record<string, unknown> | null;
  is_pinned: boolean;
  is_archived: boolean;
  created_at: string | null;
  updated_at: string | null;
  last_accessed_at: string | null;
}> {
  return requestcontexta(`/v1/memories/${id}`);
}

export async function getEntityGraph(userId: string): Promise<GraphResponse> {
  return requestcontexta<GraphResponse>(`/v1/entities/graph/${userId}`);
}

export async function listcontextaApiKeys(): Promise<ApiKey[]> {
  try {
    return requestcontexta<ApiKey[]>("/v1/keys");
  } catch {
    return [];
  }
}

export async function createcontextaApiKey(input: {
  name: string;
  scopes: string[];
}): Promise<CreatedApiKey> {
  return requestcontexta<CreatedApiKey>("/v1/keys", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
