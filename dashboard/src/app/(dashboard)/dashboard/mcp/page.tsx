import { requireSession } from "@/lib/auth-helpers";
import { listApiKeysAction } from "@/app/actions";
import { McpClientView } from "./mcp-client-view";

export const revalidate = 0;

export default async function McpPage() {
  const session = await requireSession();
  const keys = await listApiKeysAction();
  const latestKey = Array.isArray(keys) && keys.length > 0 ? keys[0] : null;

  const apiKey = latestKey?.key ?? latestKey?.prefix ?? "mk_live_contexta_default";
  const userId = session.user.id;
  const orgId = session.user.org_id;
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
