import { listApiKeysAction } from "@/app/actions";
import { resolveOperatorIdentity } from "@/lib/dashboard-identity";
import { SetupView } from "./setup-view";

export const revalidate = 0;

export default async function SetupPage() {
  const identity = await resolveOperatorIdentity();
  const keys = await listApiKeysAction();
  const latestKey = Array.isArray(keys) && keys.length > 0 ? keys[0] : null;
  const apiUrl = process.env.CONTEXTA_API_URL ?? "http://localhost:8000";

  return (
    <main className="pb-12">
      <SetupView
        userId={identity.userId ?? ""}
        orgId={identity.orgId ?? ""}
        apiKey={latestKey?.prefix ? `${latestKey.prefix}...` : "mk_live_your_api_key"}
        apiUrl={apiUrl}
      />
    </main>
  );
}
