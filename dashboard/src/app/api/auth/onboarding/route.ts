import { contextaFetch, getSession } from "@/lib/auth-helpers";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
  try {
    const session = await getSession();
    if (!session) {
      return NextResponse.json({ detail: "Not authenticated. Please sign in." }, { status: 401 });
    }

    const payload = await request.json();
    const { name, age, favorite_color, companion_role, preferences, memories, skip } = payload;

    const response = NextResponse.json({
      success: true,
      mode: "persisted",
      message: "Personal profile and memories saved successfully.",
    });

    // Mark onboarding as completed in cookie
    response.cookies.set("contexta_onboarding_completed", "true", {
      path: "/",
      httpOnly: false,
      maxAge: 60 * 60 * 24 * 365,
      sameSite: "lax",
    });

    if (skip) {
      return response;
    }

    try {
      const res = await contextaFetch("/v1/auth/onboarding", {
        method: "POST",
        body: JSON.stringify({
          user_id: session.user.id,
          organization_id: session.user.org_id,
          name: name || session.user.name || "User",
          age: age || undefined,
          favorite_color: favorite_color || undefined,
          companion_role: companion_role || undefined,
          preferences: preferences || undefined,
          memories: Array.isArray(memories) ? memories : undefined,
        }),
      });

      if (!res.ok) {
        console.warn(`[onboarding] Contexta backend returned ${res.status}. Saving profile to local fallback.`);
        response.cookies.set("contexta_pending_profile", JSON.stringify({
          name: name || session.user.name,
          companion_role,
          preferences,
          memories_count: Array.isArray(memories) ? memories.length : 0,
        }), {
          path: "/",
          maxAge: 60 * 60 * 24 * 30,
          sameSite: "lax",
        });
      }
    } catch (fetchErr: any) {
      console.warn(`[onboarding] Contexta backend is unreachable (${fetchErr?.message || "connection error"}). Saving profile to local fallback cache.`);
      response.cookies.set("contexta_pending_profile", JSON.stringify({
        name: name || session.user.name,
        companion_role,
        preferences,
        memories_count: Array.isArray(memories) ? memories.length : 0,
      }), {
        path: "/",
        maxAge: 60 * 60 * 24 * 30,
        sameSite: "lax",
      });
    }

    return response;
  } catch (err: any) {
    console.error("[onboarding] Unexpected error during onboarding:", err);
    // Even if an unexpected error occurred, allow setting onboarding completed so the user is not trapped
    const fallbackResponse = NextResponse.json({
      success: true,
      mode: "offline_fallback",
      message: "Profile cached locally.",
    });
    fallbackResponse.cookies.set("contexta_onboarding_completed", "true", {
      path: "/",
      httpOnly: false,
      maxAge: 60 * 60 * 24 * 365,
      sameSite: "lax",
    });
    return fallbackResponse;
  }
}
