"use server";

import { redirect } from "next/navigation";
import { signIn, signOut } from "@/lib/auth";
import { AuthError } from "next-auth";
import { contextaFetch, getSession } from "@/lib/auth-helpers";

export async function signInAction(formData: FormData) {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");
  try {
    await signIn("credentials", { email, password, redirectTo: "/dashboard" });
  } catch (e) {
    if (e instanceof AuthError) {
      const message = e.type === "CredentialsSignin"
        ? "Invalid email or password"
        : "Authentication failed";
      redirect(`/sign-in?error=${encodeURIComponent(message)}`);
    }
    throw e;
  }
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
      let message = "Sign up failed. Please try again.";
      try {
        const body = await res.json();
        if (body?.detail) message = body.detail;
      } catch {
        const text = await res.text();
        if (text) message = text;
      }
      return { error: message };
    }
  } catch {
    return { error: "Unable to connect to backend. Please try again." };
  }

  redirect("/sign-in?success=Account created successfully. Please sign in.");
}

export async function signOutAction() {
  await signOut({ redirect: false });
  redirect("/");
}

export async function createApiKeyAction(formData: FormData) {
  const name = String(formData.get("name") ?? "");
  const scopesRaw = String(formData.get("scopes") ?? "read,write");
  const scopes = scopesRaw.split(",").map((s) => s.trim()).filter(Boolean);

  const session = await getSession();
  if (!session) {
    return { error: "Not authenticated." };
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
        organization_id: session.user.org_id,
        actor_id: session.user.id,
      }),
    });
    if (!res.ok) {
      let message = "Failed to create API key.";
      try {
        const body = await res.json();
        if (body?.detail) message = body.detail;
      } catch {
        const text = await res.text();
        if (text) message = text;
      }
      return { error: message };
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

export async function getMemoriesAction(query?: string, limit = 50) {
  try {
    const session = await getSession();
    const res = await contextaFetch("/v1/retrieve", {
      method: "POST",
      body: JSON.stringify({
        query_text: query ?? "",
        limit,
        user_id: session?.user.id,
        organization_id: session?.user.org_id,
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
    const session = await getSession();
    if (!session?.user.id) return { nodes: [], edges: [] };
    const res = await contextaFetch(`/v1/entities/graph/${session.user.id}`);
    if (!res.ok) return { nodes: [], edges: [] };
    return await res.json();
  } catch {
    return { nodes: [], edges: [] };
  }
}

export async function signInWithGoogleAction() {
  const { signIn } = await import("@/lib/auth");
  await signIn("google", { redirectTo: "/dashboard" });
}

export async function signInWithGitHubAction() {
  const { signIn } = await import("@/lib/auth");
  await signIn("github", { redirectTo: "/dashboard" });
}

export async function getEngineStatusAction() {
  try {
    const res = await contextaFetch("/v1/system/engine-status");
    if (!res.ok) {
      return {
        node_online: false,
        current_mode: "offline",
        active_engine: "local_qwen",
        local_model_server: {
          status: "offline",
          embedding_model: { name: "Qwen/Qwen3-Embedding-0.6B", avg_latency_ms: 0 },
          reranker_model: { name: "Qwen/Qwen3-Reranker-0.6B", avg_latency_ms: 0 },
          ram_usage_mb: 0,
        },
        cloud_providers: {
          fully_configured: false,
          llm: { provider: "openai", configured: false },
          embedding: { provider: "openai", configured: false },
        },
      };
    }
    const data = await res.json();
    return { ...data, node_online: true };
  } catch {
    return {
      node_online: false,
      current_mode: "offline",
      active_engine: "local_qwen",
      local_model_server: {
        status: "offline",
        embedding_model: { name: "Qwen/Qwen3-Embedding-0.6B", avg_latency_ms: 0 },
        reranker_model: { name: "Qwen/Qwen3-Reranker-0.6B", avg_latency_ms: 0 },
        ram_usage_mb: 0,
      },
      cloud_providers: {
        fully_configured: false,
        llm: { provider: "openai", configured: false },
        embedding: { provider: "openai", configured: false },
      },
    };
  }
}

export async function setEngineModeAction(mode: "offline" | "online" | "auto") {
  try {
    const res = await contextaFetch("/v1/system/engine-mode", {
      method: "POST",
      body: JSON.stringify({ mode }),
    });
    if (!res.ok) {
      let detail = "Failed to update engine mode";
      try {
        const body = await res.json();
        if (body?.detail) detail = body.detail;
      } catch {
        // ignore
      }
      return { error: detail };
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
      return { valid: false, errors: ["Backend validation endpoint returned an error."] };
    }
    return await res.json();
  } catch (err: any) {
    return { valid: false, errors: [err?.message || "Could not reach backend."] };
  }
}

export async function ingestObservationAction(input: {
  userId?: string;
  sessionId?: string;
  messages: Array<{ role: string; content: string }>;
}) {
  try {
    const session = await getSession();
    if (!session) {
      return { error: "Not authenticated" };
    }

    const userId = input.userId || session.user.id;
    const orgId = session.user.org_id || "00000000-0000-0000-0000-000000000001";
    const sessionId = input.sessionId || crypto.randomUUID();

    const res = await contextaFetch("/v1/observations", {
      method: "POST",
      body: JSON.stringify({
        user_id: userId,
        organization_id: orgId,
        session_id: sessionId,
        messages: input.messages,
      }),
    });

    if (!res.ok) {
      const errText = await res.text();
      return { error: errText || "Failed to ingest observation" };
    }

    const data = await res.json();
    return { data };
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
    redirect("/reset-password?error=" + encodeURIComponent("New password must be at least 8 characters."));
  }
  if (newPassword !== confirmPassword) {
    redirect("/reset-password?error=" + encodeURIComponent("Passwords do not match."));
  }
  if (newPassword === currentPassword) {
    redirect("/reset-password?error=" + encodeURIComponent("New password must be different from current default password."));
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
      errorMessage = "Failed to update master password.";
      try {
        const body = await res.json();
        if (body?.detail) errorMessage = body.detail;
      } catch {
        const text = await res.text();
        if (text) errorMessage = text;
      }
    }
  } catch {
    errorMessage = "Unable to connect to Contexta backend.";
  }

  if (errorMessage) {
    redirect("/reset-password?error=" + encodeURIComponent(errorMessage));
  }

  // Terminate session so user must authenticate with their new master password
  try {
    await signOut({ redirect: false });
  } catch {
    // Ignore signOut errors if session expired
  }

  redirect("/sign-in?success=" + encodeURIComponent("Master password updated successfully. Sign in with your new credentials."));
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
    redirect("/emergency-reset?error=" + encodeURIComponent("You must type 'WIPE' to confirm permanent cryptographic shredding."));
  }
  if (newPassword.length < 8) {
    redirect("/emergency-reset?error=" + encodeURIComponent("New password must be at least 8 characters."));
  }
  if (newPassword !== confirmPassword) {
    redirect("/emergency-reset?error=" + encodeURIComponent("Passwords do not match."));
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
      errorMessage = "Failed to perform emergency wipe.";
      try {
        const body = await res.json();
        if (body?.detail) errorMessage = body.detail;
      } catch {
        const text = await res.text();
        if (text) errorMessage = text;
      }
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
    // Ignore
  }

  redirect("/sign-in?success=" + encodeURIComponent("Vault shredded and password reset. Authenticate with your new password."));
}

export async function completeOnboardingAction(formData: FormData) {
  const session = await getSession();
  if (!session) {
    redirect("/sign-in?error=" + encodeURIComponent("Not authenticated. Please sign in again."));
  }

  const isSkip = formData.get("skip") === "true";
  const name = isSkip ? (session.user.name || "User") : String(formData.get("name") ?? "").trim() || "User";
  const age = isSkip ? undefined : String(formData.get("age") ?? "").trim() || undefined;
  const favoriteColor = isSkip ? undefined : String(formData.get("favoriteColor") ?? "").trim() || undefined;
  const companionRole = isSkip ? undefined : String(formData.get("companionRole") ?? "").trim() || undefined;
  const preferences = isSkip ? undefined : String(formData.get("preferences") ?? "").trim() || undefined;

  let errorMessage: string | null = null;
  try {
    const res = await contextaFetch("/v1/auth/onboarding", {
      method: "POST",
      body: JSON.stringify({
        user_id: session.user.id,
        organization_id: session.user.org_id,
        name,
        age,
        favorite_color: favoriteColor,
        companion_role: companionRole,
        preferences,
      }),
    });

    if (!res.ok) {
      errorMessage = "Failed to save personal profile.";
      try {
        const body = await res.json();
        if (body?.detail) errorMessage = body.detail;
      } catch {
        const text = await res.text();
        if (text) errorMessage = text;
      }
    }
  } catch {
    errorMessage = "Unable to reach Contexta backend.";
  }

  if (errorMessage) {
    redirect("/onboarding?error=" + encodeURIComponent(errorMessage));
  }

  redirect("/dashboard");
}
