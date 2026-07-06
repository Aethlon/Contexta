import { listApiKeysAction } from "@/app/actions";
import { ApiKeyManager } from "@/components/api-key-manager";

export const revalidate = 0;

export default async function ApiKeysPage() {
  const keys = await listApiKeysAction();
  return <ApiKeyManager initialKeys={keys as any[]} />;
}
