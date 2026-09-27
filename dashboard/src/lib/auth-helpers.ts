import {
  CONTEXTA_API_BASE,
  identityHeaders,
  resolveOperatorIdentity,
} from "@/lib/dashboard-identity";

export {
  resolveOperatorIdentity,
  identityHeaders,
  isAuthRequired,
} from "@/lib/dashboard-identity";
export type { OperatorIdentity } from "@/lib/dashboard-identity";

const FETCH_TIMEOUT_MS = 15000;

/**
 * The single data path from the dashboard to the Python API.
 *
 * Every server action and page in `src/app` goes through this, per AGENTS.md.
 * It resolves the operator's tenant (session, cookie or bootstrap API key) and
 * attaches the identity headers the API's authentication middleware requires.
 */
export async function contextaFetch(
  path: string,
  options?: RequestInit,
): Promise<Response> {
  const identity = await resolveOperatorIdentity();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...identityHeaders(identity),
    ...(options?.headers as Record<string, string>),
  };
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    return await fetch(`${CONTEXTA_API_BASE}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
      cache: "no-store",
    });
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function readErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (body?.detail) return String(body.detail);
    if (body?.error) return String(body.error);
  } catch {
    try {
      const text = await res.text();
      if (text) return text;
    } catch {
      // Ignored: the body was already consumed or the stream errored.
    }
  }
  return fallback;
}
