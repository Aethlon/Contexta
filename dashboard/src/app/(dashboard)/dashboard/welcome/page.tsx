import { listApiKeysAction, listMemoriesAction } from "@/app/actions";
import { WelcomeView } from "./welcome-view";

export const revalidate = 0;

export default async function WelcomePage() {
  const [keys, memories] = await Promise.all([
    listApiKeysAction(),
    listMemoriesAction({ limit: 1 }),
  ]);

  const keyCount = Array.isArray(keys) ? keys.length : 0;
  const memoryCount = Array.isArray(memories) ? memories.length : 0;

  return (
    <main className="pb-12">
      <WelcomeView keyCount={keyCount} memoryCount={memoryCount} />
    </main>
  );
}
