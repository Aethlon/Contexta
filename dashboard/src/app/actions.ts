"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { signOut } from "@/lib/auth";
import {
  contextaFetch,
  readErrorDetail,
  resolveOperatorIdentity,
} from "@/lib/auth-helpers";
import { TENANT_COOKIE, type TenantOverride } from "@/lib/dashboard-identity";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function looksLikeUuid(value: string): boolean {
  return UUID_RE.test(value.trim());
}

export async function signUpAction(formData: FormData) {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");
  const confirmPassword = String(formData.get("confirmPassword") ?? "");

  if (!email.includes("@")) {
    return { error: "Please enter a valid email address." };
  }
  if (password.length < 8) {
    return { error: "Password must be at least 8 characters." };
  }
  if (password !== confirmPassword) {
    return { error: "Passwords do not match." };
  }

  try {
    const res = await contextaFetch("/v1/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      return { error: await readErrorDetail(res, "Sign up failed. Please try again.") };
    }
  } catch {
    return { error: "Unable to connect to backend. Please try again." };
  }

  redirect("/sign-in?success=Account created successfully. Please sign in.");
}

export async function signOutAction() {
  await signOut({ redirect: false });
  redirect("/dashboard");
}

/**
 * Point the console at a different organization / actor / bootstrap key.
 *
 * Stored in a cookie rather than env so the operator can switch tenant from the
 * UI without editing the deployment. The API re-checks every header we send, so
 * a mismatch surfaces as a 403 instead of reading another tenant's rows.
 */
export async function setTenantAction(formData: FormData) {
  const orgId = String(formData.get("org_id") ?? "").trim();
  const userId = String(formData.get("user_id") ?? "").trim();
  const apiKey = String(formData.get("api_key") ?? "").trim();
  const mode = String(formData.get("mode") ?? "override");

  if (mode === "reset") {
    const store = await cookies();
    store.delete(TENANT_COOKIE);
    revalidatePath("/", "layout");
    return { ok: true, cleared: true };
  }

  if (orgId && !looksLikeUuid(orgId)) {
    return { error: "Organization ID must be a UUID." };
  }
  if (userId && !looksLikeUuid(userId)) {
    return { error: "User ID must be a UUID." };
  }
  if (!orgId && !userId && !apiKey) {
    return { error: "Provide an organization ID, a user ID, or an API key." };
  }

  const override: TenantOverride = {};
  if (orgId) override.org_id = orgId;
  if (userId) override.user_id = userId;
  if (apiKey) override.api_key = apiKey;

  const store = await cookies();
  store.set(TENANT_COOKIE, encodeURIComponent(JSON.stringify(override)), {
    path: "/",
    httpOnly: true,
    sameSite: "lax",
    maxAge: 60 * 60 * 24 * 365,
  });

  revalidatePath("/", "layout");
  return { ok: true, cleared: false };
}

/**
 * Ask the API which organization the current identity actually resolves to.
 * This is the operator-facing proof that the console is pointed somewhere real.
 */
export async function probeTenantAction() {
  const identity = await resolveOperatorIdentity();
  if (!identity.resolved) {
    return {
      ok: false,
      resolvedOrgId: null,
      keyCount: 0,
      error:
        "No organization resolved. Set CONTEXTA_DASHBOARD_API_KEY (or use the tenant panel below) before the console can read data.",
    };
  }
  try {
    const res = await contextaFetch("/v1/keys");
    if (!res.ok) {
      return {
        ok: false,
        resolvedOrgId: null,
        keyCount: 0,
        error: await readErrorDetail(res, `API returned ${res.status}.`),
      };
    }
    const keys = (await res.json()) as Array<{ organization_id?: string }>;
    const resolvedOrgId =
      keys.find((k) => typeof k?.organization_id === "string")?.organization_id ??
      null;
    return { ok: true, resolvedOrgId, keyCount: keys.length, error: null };
  } catch (err) {
    return {
      ok: false,
      resolvedOrgId: null,
      keyCount: 0,
      error: err instanceof Error ? err.message : "Could not reach the API.",
    };
  }
}

export async function createApiKeyAction(formData: FormData) {
  const name = String(formData.get("name") ?? "");
  const scopesRaw = String(formData.get("scopes") ?? "read,write");
  const scopes = scopesRaw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  const identity = await resolveOperatorIdentity();
  if (!identity.orgId || !identity.userId) {
    return { error: "No organization/actor resolved for this console." };
  }
  if (!name) {
    return { error: "Key name is required." };
  }

  try {
    const res = await contextaFetch("/v1/keys", {
      method: "POST",
      body: JSON.stringify({
        name,
        scopes,
        organization_id: identity.orgId,
        actor_id: identity.userId,
      }),
    });
    if (!res.ok) {
      return { error: await readErrorDetail(res, "Failed to create API key.") };
    }
    return { data: await res.json() };
  } catch {
    return { error: "Unable to connect to backend." };
  }
}

export async function listApiKeysAction() {
  try {
    const res = await contextaFetch("/v1/keys");
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export async function revokeApiKeyAction(keyId: string): Promise<boolean> {
  try {
    const res = await contextaFetch(`/v1/keys/${keyId}`, { method: "DELETE" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function listMemoriesAction(params?: {
  memory_type?: string;
  state?: string;
  pinned?: boolean;
  limit?: number;
}) {
  try {
    const search = new URLSearchParams();
    if (params?.memory_type) search.set("memory_type", params.memory_type);
    if (params?.state) search.set("state", params.state);
    if (params?.pinned !== undefined) search.set("pinned", String(params.pinned));
    search.set("limit", String(params?.limit ?? 50));
    const res = await contextaFetch(`/v1/memories?${search.toString()}`);
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export async function deleteMemoryAction(memoryId: string) {
  try {
    const res = await contextaFetch(`/v1/memories/${memoryId}`, {
      method: "DELETE",
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function getMemoriesAction(query?: string, limit = 50) {
  try {
    const identity = await resolveOperatorIdentity();
    const res = await contextaFetch("/v1/retrieve", {
      method: "POST",
      body: JSON.stringify({
        query_text: query ?? "",
        limit,
        user_id: identity.userId ?? undefined,
        organization_id: identity.orgId ?? undefined,
      }),
    });
    if (!res.ok) return [];
    const data = await res.json();
    const raw = data.memories ?? data.results ?? data;
    if (Array.isArray(raw) && raw.length > 0 && raw[0]?.memory) {
      return raw.map((r: any) => r.memory);
    }
    return raw;
  } catch {
    return [];
  }
}

export async function getAuditLogAction(limit = 10) {
  try {
    const res = await contextaFetch(`/v1/audit?limit=${limit}`);
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export async function getGraphAction() {
  try {
    const identity = await resolveOperatorIdentity();
    if (!identity.userId) return { nodes: [], edges: [] };
    const res = await contextaFetch(`/v1/entities/graph/${identity.userId}`);
    if (!res.ok) return { nodes: [], edges: [] };
    return await res.json();
  } catch {
    return { nodes: [], edges: [] };
  }
}

/**
 * The real v1.5 record: the `structured_data.fact` triple, its validity window,
 * and the supersession lineage from the truth engine (MemoryVersion.valid_to /
 * superseded_by_id). Loaded on expand so the list view stays one query.
 */
export async function getMemoryDetailAction(memoryId: string) {
  try {
    const [detailRes, explainRes] = await Promise.all([
      contextaFetch(`/v1/memories/${memoryId}`),
      contextaFetch(`/v1/memories/${memoryId}/explain`),
    ]);
    if (!detailRes.ok) return null;
    const detail = await detailRes.json();
    const explain = explainRes.ok ? await explainRes.json() : null;
    return { detail, lineage: explain?.supersession_history ?? null };
  } catch {
    return null;
  }
}

export async function getEngineStatusAction() {
  const offlineFallback = {
    node_online: false,
    current_mode: "offline",
    active_engine: "local_qwen",
    local_model_server: {
      status: "offline",
      embedding_model: {
        name: "Qwen/Qwen3-Embedding-0.6B",
        avg_latency_ms: 0,
      },
      reranker_model: {
        name: "Qwen/Qwen3-Reranker-0.6B",
        avg_latency_ms: 0,
      },
      ram_usage_mb: 0,
    },
    cloud_providers: {
      fully_configured: false,
      llm: { provider: "openai", configured: false },
      embedding: { provider: "openai", configured: false },
    },
  };
  try {
    const res = await contextaFetch("/v1/system/engine-status");
    if (!res.ok) return offlineFallback;
    const data = await res.json();
    return { ...data, node_online: true };
  } catch {
    return offlineFallback;
  }
}

export async function setEngineModeAction(mode: "offline" | "online" | "auto") {
  try {
    const res = await contextaFetch("/v1/system/engine-mode", {
      method: "POST",
      body: JSON.stringify({ mode }),
    });
    if (!res.ok) {
      return {
        error: await readErrorDetail(res, "Failed to update engine mode"),
      };
    }
    return await res.json();
  } catch (err: any) {
    return { error: err?.message || "Failed to communicate with engine" };
  }
}

export async function validateProvidersAction(payload: {
  llm_provider: string;
  llm_api_key?: string;
  llm_model: string;
  embedding_provider: string;
  embedding_api_key?: string;
  embedding_model: string;
}) {
  try {
    const res = await contextaFetch("/v1/system/validate-providers", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      return {
        valid: false,
        errors: [await readErrorDetail(res, "Backend validation failed.")],
      };
    }
    return await res.json();
  } catch (err: any) {
    return {
      valid: false,
      errors: [err?.message || "Could not reach backend."],
    };
  }
}

export async function ingestObservationAction(input: {
  userId?: string;
  sessionId?: string;
  messages: Array<{ role: string; content: string }>;
}) {
  try {
    const identity = await resolveOperatorIdentity();
    if (!identity.orgId) {
      return { error: "No organization resolved for this console." };
    }

    const userId = input.userId || identity.userId;
    if (!userId) {
      return {
        error:
          "No actor resolved. Set a user ID in the tenant panel, or configure CONTEXTA_DASHBOARD_USER_ID.",
      };
    }

    const res = await contextaFetch("/v1/observations", {
      method: "POST",
      body: JSON.stringify({
        user_id: userId,
        organization_id: identity.orgId,
        session_id: input.sessionId || crypto.randomUUID(),
        messages: input.messages,
      }),
    });

    if (!res.ok) {
      return { error: await readErrorDetail(res, "Failed to ingest observation") };
    }

    return { data: await res.json() };
  } catch (err: any) {
    return { error: err?.message || "Failed to connect to backend" };
  }
}

export async function resetPasswordAction(formData: FormData) {
  const email = String(formData.get("email") ?? "").trim();
  const currentPassword = String(formData.get("currentPassword") ?? "");
  const newPassword = String(formData.get("newPassword") ?? "");
  const confirmPassword = String(formData.get("confirmPassword") ?? "");

  if (!email || !currentPassword || !newPassword) {
    redirect("/reset-password?error=" + encodeURIComponent("All fields are required."));
  }
  if (newPassword.length < 8) {
    redirect(
      "/reset-password?error=" +
        encodeURIComponent("New password must be at least 8 characters."),
    );
  }
  if (newPassword !== confirmPassword) {
    redirect("/reset-password?error=" + encodeURIComponent("Passwords do not match."));
  }
  if (newPassword === currentPassword) {
    redirect(
      "/reset-password?error=" +
        encodeURIComponent(
          "New password must be different from current default password.",
        ),
    );
  }

  let errorMessage: string | null = null;
  try {
    const res = await contextaFetch("/v1/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({
        email,
        current_password: currentPassword,
        new_password: newPassword,
      }),
    });
    if (!res.ok) {
      errorMessage = await readErrorDetail(res, "Failed to update master password.");
    }
  } catch {
    errorMessage = "Unable to connect to Contexta backend.";
  }

  if (errorMessage) {
    redirect("/reset-password?error=" + encodeURIComponent(errorMessage));
  }

  try {
    await signOut({ redirect: false });
  } catch {
    // Ignore signOut errors if the session had already expired.
  }

  redirect(
    "/sign-in?success=" +
      encodeURIComponent(
        "Master password updated successfully. Sign in with your new credentials.",
      ),
  );
}

export async function emergencyWipeAction(formData: FormData) {
  const email = String(formData.get("email") ?? "").trim();
  const confirmation = String(formData.get("confirmation") ?? "").trim();
  const newPassword = String(formData.get("newPassword") ?? "");
  const confirmPassword = String(formData.get("confirmPassword") ?? "");

  if (!email || !confirmation || !newPassword) {
    redirect("/emergency-reset?error=" + encodeURIComponent("All fields are required."));
  }
  if (confirmation !== "WIPE") {
    redirect(
      "/emergency-reset?error=" +
        encodeURIComponent(
          "You must type 'WIPE' to confirm permanent cryptographic shredding.",
        ),
    );
  }
  if (newPassword.length < 8) {
    redirect(
      "/emergency-reset?error=" +
        encodeURIComponent("New password must be at least 8 characters."),
    );
  }
  if (newPassword !== confirmPassword) {
    redirect(
      "/emergency-reset?error=" + encodeURIComponent("Passwords do not match."),
    );
  }

  let errorMessage: string | null = null;
  try {
    const res = await contextaFetch("/v1/auth/emergency-wipe-reset", {
      method: "POST",
      body: JSON.stringify({
        email,
        confirmation,
        new_password: newPassword,
      }),
    });
    if (!res.ok) {
      errorMessage = await readErrorDetail(
        res,
        "Failed to perform emergency wipe.",
      );
    }
  } catch {
    errorMessage = "Unable to connect to Contexta backend.";
  }

  if (errorMessage) {
    redirect("/emergency-reset?error=" + encodeURIComponent(errorMessage));
  }

  try {
    await signOut({ redirect: false });
  } catch {
    // Ignore.
  }

  redirect(
    "/sign-in?success=" +
      encodeURIComponent(
        "Vault shredded and password reset. Authenticate with your new password.",
      ),
  );
}

