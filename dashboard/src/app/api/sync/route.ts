import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { contextaFetch, getSession } from "@/lib/auth-helpers";

export async function POST(request: Request) {
  try {
    const session = await getSession();
    if (!session) {
      return NextResponse.json({ detail: "Not authenticated." }, { status: 401 });
    }

    let bodyData: any = {};
    try {
      bodyData = await request.json();
    } catch {
      // Body may be empty if reading from cookie
    }

    const cookieStore = await cookies();
    const pendingProfileCookie = cookieStore.get("contexta_pending_profile")?.value;
    let pendingProfile: any = null;

    if (pendingProfileCookie) {
      try {
        pendingProfile = JSON.parse(pendingProfileCookie);
      } catch {
        // Ignored
      }
    }

    const payload = bodyData?.profile || pendingProfile;
    if (!payload) {
      return NextResponse.json({ synced: true, message: "No pending data to synchronize." });
    }

    // Attempt to push to Contexta Brain API
    const res = await contextaFetch("/v1/auth/onboarding", {
      method: "POST",
      body: JSON.stringify({
        user_id: session.user.id,
        organization_id: session.user.org_id,
        name: payload.name || session.user.name,
        companion_role: payload.companion_role,
        preferences: payload.preferences,
        memories: payload.memories || undefined,
      }),
    });

    if (!res.ok) {
      return NextResponse.json(
        { synced: false, error: "Backend rejected sync payload." },
        { status: res.status }
      );
    }

    const response = NextResponse.json({
      synced: true,
      message: "Software vault successfully synchronized with Docker PostgreSQL database.",
    });

    // Clear the pending profile cookie once persisted
    response.cookies.delete("contexta_pending_profile");

    return response;
  } catch (err: any) {
    return NextResponse.json(
      { synced: false, error: err?.message || "Sync failed. Engine may still be booting." },
      { status: 500 }
    );
  }
}
