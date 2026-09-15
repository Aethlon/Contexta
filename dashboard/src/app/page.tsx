import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth-helpers";

export default async function RootPage() {
  const session = await getSession();
  if (!session) {
    redirect("/sign-in");
  }
  if (session.user.must_reset_password) {
    redirect("/reset-password");
  }
  if (!session.user.onboarding_completed) {
    redirect("/onboarding");
  }
  redirect("/dashboard");
}
