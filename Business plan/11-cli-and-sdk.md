# 11 — CLI and SDK

This document covers the developer-facing distribution surfaces: Pip and npm SDKs, the `contexta` CLI, and how new versions are released.

The SDK is the **public product** ([18-sdk-first-product-contract.md](./18-sdk-first-product-contract.md)). This doc covers packaging, distribution, versioning, telemetry, and the CLI command surface; the method-by-method API and customer-facing contract live in doc 18.

## Decisions of record

1. **Two parallel SDKs at launch: Pip (`contexta-client`) and npm (`@contexta/client`).** Equal feature parity. Either can be the dev's first impression.
2. **CLI ships in the Pip package** as a console-script entry point. We do not build a separate Go or Rust binary at v1. Reason: dev velocity and one less artifact to sign and distribute.
3. **Both SDKs are MIT-licensed.** The engine is closed-source; the SDKs are public glue. This is standard for closed SaaS (e.g., Stripe's SDK is open, their billing engine is not).
4. **SDK versions are decoupled from the API version.** SDK 1.x → API v1, SDK 2.x → API v2.
5. **Async-first.** Both SDKs offer sync and async clients. Pip uses `httpx`, npm uses `fetch`.
6. **Auto-retry with exponential backoff** on 5xx and 429 (with `Retry-After`).

## Package layout

```
clients/
  python/
    contexta_client/
      __init__.py             # contexta class, async + sync clients
      _http.py                # httpx client, retries, instrumentation
      _types.py               # dataclasses / Pydantic models
      cli/
        __init__.py
        main.py               # Typer app entrypoint
        commands/
          login.py
          init.py
          test.py
          policy.py
          schema.py
          memory.py
          explain.py
          export.py
      adapters/
        openai/__init__.py    # Re-exported as CONTEXTA_openai
        llamaindex/__init__.py
        anthropic/__init__.py
        langchain/__init__.py
    pyproject.toml
    README.md
  typescript/
    src/
      index.ts                # contexta class
      http.ts
      types.ts
      adapters/
        openai/
        anthropic/
        langchain/
        vercel-ai/
    package.json
    README.md
```

The `contexta` engine repo (this monorepo) imports nothing from `clients/`. Clients are independent packages with their own CI.


## Pip SDK: `contexta-client`

### Install and first call

```bash
pip install contexta-client
```

```python
from contexta_client import contexta

contexta = contexta(api_key="mk_live_...", base_url="https://api.contexta.dev")

# Observe a conversation turn
contexta.observe(
    user_id="u_123",
    session_id="s_456",
    messages=[
        {"role": "user", "content": "I prefer Postgres over Mongo"},
        {"role": "assistant", "content": "Noted."},
    ],
)

# Retrieve context for the next turn
ctx = contexta.context(user_id="u_123", session_id="s_456", token_budget=1500)
print(ctx.to_system_prompt())
```

### Async client

```python
from contexta_client import Asynccontexta

contexta = Asynccontexta.from_env()

async def handle_turn(user_message: str):
    ctx = await contexta.context(user_id="u_123", session_id="s_456", query=user_message)
    return ctx.to_system_prompt()
```

`contexta.from_env()` reads `CONTEXTA_API_KEY` and `CONTEXTA_API_URL` from env vars (or `.env` via `python-dotenv` if installed).

### Public API surface

```python
class contexta:
    @classmethod
    def from_env(cls) -> "contexta": ...
    
    def __init__(self, *, api_key: str, base_url: str = "https://api.contexta.dev",
                 timeout: float = 30.0, max_retries: int = 3): ...

    # Observations
    def observe(self, *, user_id: UUID, session_id: UUID, messages: list[dict],
                metadata: dict | None = None, policy: str | None = None) -> ObserveResponse: ...
    def observe_batch(self, observations: list[dict]) -> BatchObserveResponse: ...

    # Retrieval
    def retrieve(self, *, user_id: UUID, query_text: str, ...) -> list[ScoredMemory]: ...
    def context(self, *, user_id: UUID, session_id: UUID, query: str | None = None,
                token_budget: int = 2000, include_user_model: bool = True) -> Context: ...

    # Memories
    def get_memory(self, memory_id: UUID) -> Memory: ...
    def explain(self, memory_id: UUID) -> Explanation: ...
    def pin(self, memory_id: UUID) -> Memory: ...
    def unpin(self, memory_id: UUID) -> Memory: ...
    def archive(self, memory_id: UUID) -> Memory: ...
    def restore(self, memory_id: UUID) -> Memory: ...
    def delete(self, memory_id: UUID) -> None: ...
    def timeline(self, user_id: UUID) -> list[TimelineEvent]: ...

    # Sessions
    def create_session(self, user_id: UUID, metadata: dict | None = None) -> Session: ...
    def end_session(self, session_id: UUID) -> Session: ...

    # Policies & schemas
    def register_policy(self, name: str, ...) -> Policy: ...
    def list_policies(self) -> list[Policy]: ...
    def register_schema(self, name: str, fields: list[FieldDef]) -> Schema: ...

    # Health
    def ping(self) -> dict: ...
```

### Retry and error handling

```python
class contextaError(Exception): pass
class AuthenticationError(contextaError): pass
class AuthorizationError(contextaError): pass
class ValidationError(contextaError): pass
class QuotaExceeded(contextaError): pass
class RateLimited(contextaError):
    retry_after: int  # seconds
class ServerError(contextaError): pass
```

Default retry policy: 3 attempts on 5xx and 429 with exponential backoff (1s, 2s, 4s). Honors `Retry-After`.


## npm SDK: `@contexta/client`

### Install and first call

```bash
npm install @contexta/client
# or
pnpm add @contexta/client
```

```ts
import { contexta } from "@contexta/client";

const contexta = contexta.fromEnv();
// or: new contexta({ apiKey: "mk_live_...", baseUrl: "https://api.contexta.dev" })

// Observe
await contexta.observe({
  userId: "u_123",
  sessionId: "s_456",
  messages: [
    { role: "user", content: "I prefer Postgres over Mongo" },
    { role: "assistant", content: "Noted." },
  ],
});

// Retrieve context
const ctx = await contexta.context({
  userId: "u_123",
  sessionId: "s_456",
  tokenBudget: 1500,
});

console.log(ctx.toSystemPrompt());
```

### Public API

```ts
class contexta {
  static fromEnv(): contexta;
  constructor(opts: { apiKey: string; baseUrl?: string; timeout?: number; maxRetries?: number });

  observe(input: ObserveInput): Promise<ObserveResponse>;
  observeBatch(input: ObserveInput[]): Promise<BatchObserveResponse>;

  retrieve(input: RetrieveInput): Promise<ScoredMemory[]>;
  context(input: ContextInput): Promise<Context>;

  getMemory(memoryId: string): Promise<Memory>;
  explain(memoryId: string): Promise<Explanation>;
  pin(memoryId: string): Promise<Memory>;
  unpin(memoryId: string): Promise<Memory>;
  archive(memoryId: string): Promise<Memory>;
  restore(memoryId: string): Promise<Memory>;
  delete(memoryId: string): Promise<void>;
  timeline(userId: string): Promise<TimelineEvent[]>;

  createSession(userId: string, metadata?: Record<string, unknown>): Promise<Session>;
  endSession(sessionId: string): Promise<Session>;

  registerPolicy(input: PolicyInput): Promise<Policy>;
  listPolicies(): Promise<Policy[]>;
  registerSchema(input: SchemaInput): Promise<Schema>;

  ping(): Promise<{ status: string; region: string }>;
}
```

The SDK ships ESM and CJS bundles. Tree-shakeable. Zero dependencies (uses native `fetch`, `crypto`, `URL`).

### Edge runtime support

`@contexta/client` works in:
- Node 20+
- Vercel Edge Runtime
- Cloudflare Workers
- Browser (with CORS configured by customer; not recommended without a proxy)
- Bun, Deno

The SDK avoids Node-specific APIs (`fs`, `path`, `process.versions.node`) so edge runtimes work out of the box.

## CLI: `contexta`

The CLI ships in the Pip package and is installed as a console script:

```bash
pip install contexta-client
contexta --help
```

### Commands

```
contexta --help
  contexta CLI — manage your memory layer from the terminal.

Commands:
  login            Authenticate via browser, save credentials to ~/.contexta/config.toml
  logout           Clear stored credentials
  whoami           Print the active org, project, and key

  init             Scaffold .env, integration snippet, and recommended SDK install in current dir
  test             Smoke test: ping API, send a sample observation, retrieve context

  projects list    List your projects
  projects create  Create a new project
  projects use     Set the default project for subsequent commands

  keys list        List API keys
  keys create      Create a new API key
  keys rotate      Rotate a key
  keys revoke      Revoke a key

  policies list    List policies
  policies show    Show a policy
  policies create  Register a policy from a YAML file
  policies sync    Sync policies from a directory

  schemas list     List custom schemas
  schemas create   Register a schema from a YAML file

  memories list    List memories (paginated)
  memories show    Show a memory
  memories explain Show explainability for a memory
  memories pin     Pin a memory
  memories archive Archive a memory
  memories delete  Delete a memory (with confirm)

  observations send  Send a one-off observation from a JSON file or stdin

  context get      Get context bundle for a user
  context preview  Preview context with a sample query

  usage            Show current period usage
  audit            Tail audit log (with --follow)
  export           Export memories to JSONL
```

### Sample session

```
$ contexta login
Opening browser for authentication...
✓ Logged in as alice@acme.com (Acme Inc, project: default)

$ contexta init
✓ Created .env with CONTEXTA_API_KEY and CONTEXTA_API_URL
✓ Created CONTEXTA_example.py
✓ Run: pip install contexta-client && python CONTEXTA_example.py

$ contexta test
→ Pinging api.contexta.dev...
✓ API reachable (eu-fsn1)
→ Sending sample observation...
✓ Accepted (job_id 01J9ZX...)
→ Waiting for extraction...
✓ Extracted 2 memories
→ Retrieving context...
✓ Got 2 memories
🎉 contexta is working.

$ contexta policies create --file policies/coding-agent.yaml
✓ Registered policy "coding-agent" (id 4f...)

$ contexta usage
Solo Pro plan, period 2026-05-01 to 2026-06-01
  Active memories     91,245 / 250,000
  Observations        213,400 / 500,000
  Retrievals          1,843,200 / 5,000,000
  Reranks             22,100 / 100,000
  Estimated cost: $69.00
```

The CLI reads `~/.contexta/config.toml`:

```toml
[default]
api_url = "https://api.contexta.dev"
api_key = "mk_live_..."        # alternative to login
org_id = "..."
project_id = "..."

[profiles.staging]
api_url = "https://api.contexta.dev"
api_key = "mk_test_..."
project_id = "..."
```

Profile selection: `contexta --profile=staging memories list`.


## Versioning and release

| Concept | Convention |
|---|---|
| SDK version | semver (1.4.2) |
| API version | path-prefix (`/v1/`) |
| SDK ↔ API mapping | SDK 1.x → API v1, SDK 2.x → API v2 |
| Breaking SDK change | Major bump |
| New optional methods | Minor bump |
| Bug fix | Patch bump |
| Pre-release | `1.5.0-rc.1` for npm, `1.5.0rc1` for Pip |

Release flow:

1. Open PR to `clients/python/` or `clients/typescript/`.
2. CI runs unit tests, smoke tests against a staging contexta.
3. Merge → GitHub Action runs `release-please` to draft version PR.
4. Merge release PR → tag pushed.
5. Tag triggers publish to PyPI / npm.

Pre-1.0 (during the closed beta), every minor version can break. After 1.0 (public launch), we follow strict semver for at least 24 months.

## Telemetry

The SDKs emit anonymized telemetry by default (opt-out):

- SDK version, runtime version, OS family.
- Endpoint hit, status code, duration.
- No request bodies, no API keys, no user_ids.

Disabled with `CONTEXTA_TELEMETRY=false` or `contexta({ telemetry: false })`. Documented in the README.

The data is used to:
- Detect SDK bugs (a sudden 4xx spike on `observe`).
- Decide which language/framework to prioritize.
- Plan deprecations (we know which SDK versions are still in use).

## Security

- SDKs ship a SBOM (CycloneDX format) with each release.
- We sign releases with Sigstore.
- We monitor `pip-audit` and `npm audit` weekly; security patches ship within 48h.
- The npm package is owned by a 2FA-required account.
- The PyPI package is owned by a 2FA-required account.
- The signing key is in a hardware token, not on a laptop.

## Release notes and changelog

Every release publishes:
- A GitHub Release (clients are public repos under `contexta-dev/python-client` etc).
- A CHANGELOG.md update.
- A line in the docs site's "What's new" section.
- A Slack announcement to the customer-only channel for any minor or major.

We do not break customers silently. If a release affects behavior beyond bug fixes, the release notes lead with a bold callout.
