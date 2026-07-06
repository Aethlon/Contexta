"use server";

import { redirect } from "next/navigation";
import { signIn, signOut } from "@/lib/auth";
import { contextaFetch } from "@/lib/auth-helpers";
import { AuthError } from "next-auth";

export async function signInAction(formData: FormData) {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");
  try {
    const result = await signIn("credentials", {
      email,
      password,
      redirect: false,
    });
    if (result?.error) {
      const message = result.error === "CredentialsSignin"
        ? "Invalid email or password"
        : result.error;
      redirect(`/sign-in?error=${encodeURIComponent(message)}`);
    }
  } catch (e) {
    const message = e instanceof AuthError ? "Invalid email or password" : "Authentication failed";
    redirect(`/sign-in?error=${encodeURIComponent(message)}`);
  }
  redirect("/dashboard");
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
      const detail = await res.text();
      return { error: detail || "Sign up failed. Please try again." };
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
  const scopesRaw = String(formData.get("scopes") ?? "observe,retrieve");
  const scopes = scopesRaw.split(",").map((s) => s.trim()).filter(Boolean);

  if (!name) {
    return { error: "Key name is required." };
  }

  try {
    const res = await contextaFetch("/v1/keys", {
      method: "POST",
      body: JSON.stringify({ name, scopes }),
    });
    if (!res.ok) {
      const detail = await res.text();
      return { error: detail || "Failed to create API key." };
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

export async function getUsageAction() {
  try {
    const res = await contextaFetch("/v1/usage");
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function getMemoriesAction(query?: string, limit = 50) {
  try {
    const res = await contextaFetch("/v1/retrieve", {
      method: "POST",
      body: JSON.stringify({ query_text: query ?? "", limit }),
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.memories ?? data.results ?? data;
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

export async function createCheckoutSessionAction(formData: FormData) {
  const plan = String(formData.get("plan") ?? "scale");
  try {
    const res = await contextaFetch("/v1/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ plan }),
    });
    if (res.ok) {
      const { url } = await res.json();
      if (url) redirect(url);
    }
  } catch {
    // fall through
  }
}

export async function openCustomerPortalAction() {
  try {
    const res = await contextaFetch("/v1/billing/portal", { method: "POST" });
    if (res.ok) {
      const { url } = await res.json();
      if (url) redirect(url);
    }
  } catch {
    // fall through
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
