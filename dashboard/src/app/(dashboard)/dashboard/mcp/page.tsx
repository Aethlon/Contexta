import { listApiKeysAction } from "@/app/actions";
import { resolveOperatorIdentity } from "@/lib/dashboard-identity";
import { McpClientView } from "./mcp-client-view";

export const revalidate = 0;

export default async function McpPage() {
  const identity = await resolveOperatorIdentity();
  const keys = await listApiKeysAction();
  const latestKey = Array.isArray(keys) && keys.length > 0 ? keys[0] : null;

  const apiKey = latestKey?.prefix ?? "mk_live_";
  const userId = identity.userId ?? "";
  const orgId = identity.orgId ?? "";
  const apiUrl = process.env.CONTEXTA_API_URL ?? "http://localhost:8000";

  return (
    <main className="space-y-6 pb-12">
      <McpClientView
        userId={userId}
        orgId={orgId}
        apiKey={apiKey}
        apiUrl={apiUrl}
      />
    </main>
  );
}
