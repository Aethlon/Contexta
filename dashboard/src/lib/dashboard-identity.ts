import { cache } from "react";
import { cookies } from "next/headers";

/**
 * Operator identity resolution for the dashboard.
 *
 * Contexta is a self-hosted, single-operator tool, so the console ships with page
 * auth OFF and authenticates to the Python API with a bootstrap API key instead
 * of a NextAuth session. Turning auth back on is one env var:
 *
 *   CONTEXTA_DASHBOARD_AUTH=on
 *
 * The tenant is never silently defaulted. It resolves, in order, from:
 *
 *   1. the `contexta_tenant` cookie, which the operator sets in the UI
 *   2. CONTEXTA_DASHBOARD_ORG_ID / CONTEXTA_DASHBOARD_USER_ID (+ optional key)
 *   3. CONTEXTA_DASHBOARD_API_KEY, by asking the API which org that key belongs to
 *
 * If none of those produce a tenant, the dashboard reports "unresolved" and the
 * API calls go out unauthenticated (and get a 401), rather than quietly acting on
 * some other organization's data.
 */

export const TENANT_COOKIE = "contexta_tenant";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const CONTEXTA_API_BASE = (
  process.env.CONTEXTA_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export type TenantOverride = {
  org_id?: string;
  user_id?: string;
  api_key?: string;
};

export type IdentitySource = "session" | "operator" | "env" | "discovered" | "none";

export type OperatorIdentity = {
  /** True when CONTEXTA_DASHBOARD_AUTH is on and a NextAuth session is in play. */
  authRequired: boolean;
  /** False when no organization could be resolved; API calls will be rejected. */
  resolved: boolean;
  orgId: string | null;
  userId: string | null;
  apiKey: string | null;
  source: IdentitySource;
  /** Signed-in email, when auth is on. */
  email: string | null;
  name: string | null;
};

function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID_RE.test(value.trim());
}

function envValue(name: string): string | undefined {
  const raw = process.env[name];
  if (!raw) return undefined;
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

/**
 * The single switch. Absent or unrecognised values mean OFF, which is the
 * default for a self-hosted single-operator console.
 */
export function isAuthRequired(): boolean {
  const raw = envValue("CONTEXTA_DASHBOARD_AUTH")?.toLowerCase();
  if (!raw) return false;
  return ["on", "1", "true", "yes", "required", "enabled"].includes(raw);
}

async function readTenantCookie(): Promise<TenantOverride | null> {
  try {
    const store = await cookies();
    const raw = store.get(TENANT_COOKIE)?.value;
    if (!raw) return null;
    const parsed = JSON.parse(decodeURIComponent(raw)) as TenantOverride;
    if (!parsed || typeof parsed !== "object") return null;
    return parsed;
  } catch {
    return null;
  }
}

const DISCOVERY_TIMEOUT_MS = 8000;

async function discoverOrgFromKey(apiKey: string): Promise<string | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DISCOVERY_TIMEOUT_MS);
  try {
    const res = await fetch(`${CONTEXTA_API_BASE}/v1/keys`, {
      headers: { "x-api-key": apiKey, Accept: "application/json" },
      signal: controller.signal,
      cache: "no-store",
    });
    if (!res.ok) return null;
    const keys = (await res.json()) as Array<{ organization_id?: string }>;
    const org = keys.find((k) => isUuid(k?.organization_id))?.organization_id;
    return isUuid(org) ? org : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

async function _resolveOperatorIdentity(): Promise<OperatorIdentity> {
  const authRequired = isAuthRequired();

  if (authRequired) {
    const { auth } = await import("@/lib/auth");
    const session = await auth();
    const user = session?.user as
      | { id?: string; email?: string; name?: string; org_id?: string }
      | undefined;
    if (!user?.id || !user?.org_id) {
      return {
        authRequired,
        resolved: false,
        orgId: null,
        userId: null,
        apiKey: null,
        source: "none",
        email: user?.email ?? null,
        name: user?.name ?? null,
      };
    }
    return {
      authRequired,
      resolved: true,
      orgId: user.org_id,
      userId: user.id,
      apiKey: null,
      source: "session",
      email: user.email ?? null,
      name: user.name ?? null,
    };
  }

  const envKey = envValue("CONTEXTA_DASHBOARD_API_KEY") ?? null;
  const envOrg = envValue("CONTEXTA_DASHBOARD_ORG_ID");
  const envUser = envValue("CONTEXTA_DASHBOARD_USER_ID");

  const override = await readTenantCookie();
  if (override && (isUuid(override.org_id) || isUuid(override.user_id) || override.api_key)) {
    return {
      authRequired,
      resolved: Boolean(override.org_id || override.user_id || override.api_key),
      orgId: isUuid(override.org_id) ? override.org_id : null,
      userId: isUuid(override.user_id) ? override.user_id : null,
      apiKey: override.api_key || envKey,
      source: "operator",
      email: null,
      name: null,
    };
  }

  let orgId = isUuid(envOrg) ? envOrg : null;
  let source: IdentitySource = "env";

  if (!orgId && envKey) {
    const discovered = await discoverOrgFromKey(envKey);
    if (discovered) {
      orgId = discovered;
      source = "discovered";
    }
  }

  if (!orgId && !isUuid(envUser)) {
    return {
      authRequired,
      resolved: false,
      orgId: null,
      userId: null,
      apiKey: envKey,
      source: "none",
      email: null,
      name: null,
    };
  }

  return {
    authRequired,
    resolved: true,
    orgId,
    userId: isUuid(envUser) ? envUser : null,
    apiKey: envKey,
    source,
    email: null,
    name: null,
  };
}

export const resolveOperatorIdentity = cache(_resolveOperatorIdentity);

/**
 * Headers the Python API needs to resolve a tenant.
 *
 * `AuthenticationMiddleware` accepts two independent proofs: an API key (the
 * normal path — the key itself carries both organization and actor) or the
 * legacy `x-organization-id` + `x-user-id` pair, which the API only honours when
 * it is started with CONTEXTA_ALLOW_LEGACY_TENANT_HEADERS=true. Both are emitted
 * here so either deployment shape works, and any header we do send is
 * cross-checked server-side by the API, so a wrong tenant surfaces as a 403
 * rather than as a silent read of another organization's rows.
 */
export function identityHeaders(identity: OperatorIdentity): Record<string, string> {
  const headers: Record<string, string> = {};
  if (identity.apiKey) {
    headers["x-api-key"] = identity.apiKey;
  }
  if (identity.orgId) {
    headers["x-organization-id"] = identity.orgId;
  }
  if (identity.userId) {
    headers["x-user-id"] = identity.userId;
  }
  return headers;
}
