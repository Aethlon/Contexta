# contexta Docs

Developer documentation for contexta, the self-hosted long-term memory engine for AI agents.

Nextra 2 on Next.js 14 and React 18, with MDX. The site is **not** built by the root `docker compose` stack and is not part of the Contexta runtime.

## Development

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Build

```bash
npm run lint
npm run build
npm run start
```

> **Known blocker.** `next.config.ts` is not supported by Next.js 14 — `next build` fails with `Configuring Next.js via 'next.config.ts' is not supported. Please replace the file with 'next.config.js' or 'next.config.mjs'.` Rename the file to `next.config.mjs` to build. This is a config fix, not a content problem, so it has not been done as part of the v1.5 documentation pass.

## Structure

| Route | Contents |
| :--- | :--- |
| `src/app/quickstart/` | Self-hosted quickstart, Windows and macOS/Linux |
| `src/app/concepts/` | Observations, memories, retrieval, isolation |
| `src/app/guide/` | Ingestion, OpenAI, Anthropic, LangChain, LlamaIndex, custom agents |
| `src/app/reference/` | API, SDK overview, Python SDK, TypeScript SDK, CLI, v1.5 upgrade guide |
| `src/app/examples/` | Coding, tutor, and CRM agents |
| `src/app/changelog/` | v1.5 and v1 release notes |
| `src/app/licensing/` | The dual-licence terms |
| `src/components/Sidebar.tsx` | Hand-maintained navigation — there is no `_meta` file |

## Conventions

- Pages are `.mdx`. The two files that were `.tsx` but contained raw Markdown (`quickstart/`, `concepts/`) have been converted to `.mdx`; raw Markdown in a `.tsx` file does not compile.
- `src/app/page.tsx` is a redirect to `/quickstart`.
- Long-form engineering notes live in `docs/Featuers/` as plain Markdown. They are **not** compiled by Nextra, so review their links, tables, and code fences by hand.
