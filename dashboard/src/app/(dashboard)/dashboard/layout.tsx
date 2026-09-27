import { redirect } from "next/navigation";
import { resolveOperatorIdentity } from "@/lib/dashboard-identity";
import { DashboardShell } from "@/components/dashboard-shell";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const identity = await resolveOperatorIdentity();

  // With auth enabled, a request that carries no session has to go sign in.
  // With auth disabled (the default) there is nothing to check, so the console
  // renders even when the tenant is unresolved -- the tenant panel then explains
  // why the data views are empty instead of bouncing the operator to a login.
  if (identity.authRequired && !identity.resolved) {
    redirect("/sign-in");
  }

  return <DashboardShell identity={identity}>{children}</DashboardShell>;
}
