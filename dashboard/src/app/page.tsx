import { redirect } from "next/navigation";
import { isAuthRequired } from "@/lib/dashboard-identity";

// The redirect target depends on an env var, which Next would otherwise inline
// at build time and bake into a static page.
export const dynamic = "force-dynamic";

export default async function RootPage() {
  // With page auth off (the default for a self-hosted single-operator console)
  // the root is the console itself. With it on, an unauthenticated visitor is
  // sent to the sign-in page instead.
  redirect(isAuthRequired() ? "/sign-in" : "/dashboard");
}
