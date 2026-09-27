import { listApiKeysAction } from "@/app/actions";
import { resolveOperatorIdentity } from "@/lib/dashboard-identity";
import { SettingsView } from "./settings-view";

export const revalidate = 0;

export default async function SettingsPage() {
  const identity = await resolveOperatorIdentity();
  const keys = await listApiKeysAction();
  const apiUrl = process.env.CONTEXTA_API_URL ?? "http://localhost:8000";

  return (
    <main className="pb-12">
      <SettingsView
        identity={identity}
        keys={Array.isArray(keys) ? keys : []}
        apiUrl={apiUrl}
      />
    </main>
  );
}
