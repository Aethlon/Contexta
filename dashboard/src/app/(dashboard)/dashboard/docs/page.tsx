import { resolveOperatorIdentity } from "@/lib/dashboard-identity";
import { listApiKeysAction, getEngineStatusAction } from "@/app/actions";
import { DocsView } from "./docs-view";
import type { DocContext, DocSection } from "./docs-content";
import { buildSections } from "./docs-sections";
import { mcpToolReference, mcpEndpoint } from "./mcp-reference";

export const revalidate = 0;

export default async function DocsPage() {
  const [identity, keys, engine] = await Promise.all([
    resolveOperatorIdentity(),
    listApiKeysAction(),
    getEngineStatusAction().catch(() => null),
  ]);

  const list = Array.isArray(keys) ? keys : [];

  const ctx: DocContext = {
    apiUrl: process.env.CONTEXTA_API_URL ?? "http://localhost:8000",
    mcpUrl: mcpEndpoint(),
    orgId: identity.orgId ?? "",
    userId: identity.userId ?? "",
    keyPrefix: list[0]?.prefix ?? null,
    hasKey: list.length > 0,
    engine: {
      extractionModel:
        engine?.extraction?.default_model ?? engine?.extraction?.model ?? "unknown",
      extractionStatus: engine?.extraction?.status ?? "unknown",
      embeddingModel:
        engine?.local_model_server?.embedding_model?.name ?? "Qwen/Qwen3-Embedding-0.6B",
      rerankerModel:
        engine?.local_model_server?.reranker_model?.name ?? "Qwen/Qwen3-Reranker-0.6B",
      embeddingProfile:
        engine?.local_model_server?.embedding_model?.profile ?? "offline-qwen3-1024",
      dimensions: engine?.local_model_server?.embedding_model?.dimensions ?? 1024,
    },
    tools: mcpToolReference(),
  };

  const sections: DocSection[] = buildSections(ctx);

  return (
    <div className="pb-12">
      <DocsView ctx={ctx} sections={sections} />
    </div>
  );
}
