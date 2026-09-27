import { NextResponse, type NextRequest } from "next/server";
import { isAuthRequired } from "@/lib/dashboard-identity";

export const dynamic = "force-dynamic";

const DISABLED = () =>
  NextResponse.json(
    {
      error: "authentication_disabled",
      detail:
        "CONTEXTA_DASHBOARD_AUTH is not 'on'. The console has no sign-in; open /dashboard.",
    },
    { status: 404 },
  );

/**
 * NextAuth is only mounted when CONTEXTA_DASHBOARD_AUTH=on. Left mounted
 * unconditionally it would advertise a login endpoint on a console that has no
 * login, so the default configuration answers 404 with the reason.
 */
export async function GET(request: NextRequest) {
  if (!isAuthRequired()) return DISABLED();
  const { handlers } = await import("@/lib/auth");
  return handlers.GET(request);
}

export async function POST(request: NextRequest) {
  if (!isAuthRequired()) return DISABLED();
  const { handlers } = await import("@/lib/auth");
  return handlers.POST(request);
}
