import { requireSession } from "@/lib/auth-helpers";
import { listApiKeysAction } from "@/app/actions";
import { SettingsView } from "./settings-view";

export const revalidate = 0;

export default async function SettingsPage() {
  const session = await requireSession();
  const keys = await listApiKeysAction();
  const apiUrl = process.env.CONTEXTA_API_URL ?? "http://localhost:8000";

  return (
    <main className="pb-12">
      <SettingsView session={session} keys={Array.isArray(keys) ? keys : []} apiUrl={apiUrl} />
    </main>
  );
}
