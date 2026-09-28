import { listApiKeysAction } from "@/app/actions";
import { McpClientView } from "./mcp-client-view";

export const revalidate = 0;

export default async function McpPage() {
  const keys = await listApiKeysAction();
  const apiUrl = process.env.CONTEXTA_API_URL ?? "http://localhost:8000";

  // NOTE: the full API key is deliberately NOT read here.
  //
  // Only a SHA-256 hash and a 16-character display prefix are ever stored, so a
  // previously-created key cannot be shown. The previous version of this page
  // passed `key.prefix` into the config snippets, which handed every user a
  // snippet containing an unusable placeholder. The view now mints a key
  // in-place (the token is returned exactly once) or accepts a pasted one.
  const existingKeys = Array.isArray(keys)
    ? keys.map((k) => ({ id: k.id, name: k.name, prefix: k.prefix, created_at: k.created_at }))
    : [];

  return (
    <main className="pb-12">
      <McpClientView apiUrl={apiUrl} existingKeys={existingKeys} />
    </main>
  );
}
