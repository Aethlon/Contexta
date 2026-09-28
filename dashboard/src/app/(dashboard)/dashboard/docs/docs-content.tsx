import { CopyButton } from "./copy-button";

export interface DocContext {
  apiUrl: string;
  mcpUrl: string;
  orgId: string;
  userId: string;
  keyPrefix: string | null;
  hasKey: boolean;
  /** Live engine telemetry, so the docs never drift from the running system. */
  engine: {
    extractionModel: string;
    extractionStatus: string;
    embeddingModel: string;
    rerankerModel: string;
    embeddingProfile: string;
    dimensions: number;
  };
  /** Tool names and required args, read from the live MCP server. */
  tools: { name: string; required: string[]; optional: string[] }[];
}

export type DocBlock =
  | { kind: "prose"; text: string }
  | { kind: "note"; tone: "info" | "warn"; title: string; text: string }
  | { kind: "code"; label?: string; lang: string; code: string }
  | { kind: "table"; head: string[]; rows: string[][] }
  | { kind: "list"; items: string[] };

export interface DocSection {
  id: string;
  title: string;
  blurb: string;
  blocks: DocBlock[];
}

export function DocsContent({
  section,
  ctx,
}: {
  section: DocSection;
  ctx: DocContext;
}) {
  return (
    <article className="min-w-0">
      <header className="mb-6">
        <h1 className="nb-page-title">{section.title}</h1>
        <p className="nb-page-subtitle">{section.blurb}</p>
      </header>

      <div className="space-y-6">
        {section.blocks.map((block, i) => {
          switch (block.kind) {
            case "prose":
              return (
                <p key={i} className="text-[13px] leading-relaxed text-muted-foreground">
                  {block.text}
                </p>
              );

            case "note": {
              const accent =
                block.tone === "warn" ? "var(--accent-yellow)" : "var(--accent-blue)";
              return (
                <div
                  key={i}
                  className="rounded-lg border p-3.5"
                  style={{
                    borderColor: `color-mix(in srgb, ${accent} 32%, transparent)`,
                    background: `color-mix(in srgb, ${accent} 7%, transparent)`,
                  }}
                >
                  <p className="text-[13px] font-medium" style={{ color: accent }}>
                    {block.title}
                  </p>
                  <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
                    {block.text}
                  </p>
                </div>
              );
            }

            case "code":
              return (
                <div key={i}>
                  {block.label && (
                    <p className="mb-1.5 text-xs text-muted-foreground">{block.label}</p>
                  )}
                  <div className="relative">
                    <pre className="overflow-x-auto rounded-lg border border-border bg-muted p-3.5 font-mono text-xs leading-relaxed text-foreground">
                      {block.code}
                    </pre>
                    <CopyButton text={block.code} />
                  </div>
                </div>
              );

            case "table":
              return (
                <div key={i} className="overflow-x-auto rounded-lg border border-border">
                  <table className="w-full text-[13px]">
                    <thead>
                      <tr className="border-b border-border">
                        {block.head.map((h) => (
                          <th
                            key={h}
                            className="px-3 py-2 text-left text-xs font-medium text-muted-foreground"
                          >
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {block.rows.map((row, r) => (
                        <tr key={r} className="border-b border-border last:border-0">
                          {row.map((cell, c) => (
                            <td key={c} className="px-3 py-2 align-top text-muted-foreground">
                              {c === 1 && cell.startsWith("/") ? (
                                <code className="nb-code">{cell}</code>
                              ) : (
                                cell
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );

            case "list":
              return (
                <ul key={i} className="space-y-1.5 text-[13px] leading-relaxed text-muted-foreground">
                  {block.items.map((item) => (
                    <li key={item} className="flex gap-2">
                      <span className="mt-[7px] size-1 shrink-0 rounded-full bg-muted-foreground/50" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              );
          }
        })}
      </div>
    </article>
  );
}
