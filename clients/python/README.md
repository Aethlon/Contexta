# contexta Python SDK

Persistent memory layer for AI agents. Built for agent developers who need their agents to remember user preferences, facts, and context across sessions.

## Installation

```bash
pip install contexta-client
```

## Quick start

```python
from uuid import uuid4

from contexta_client import Contexta

with Contexta.from_env() as m:  # reads CONTEXTA_API_KEY
    user_id = str(uuid4())
    session_id = str(uuid4())

    # Remember
    m.observe(
        user_id=user_id,
        session_id=session_id,
        messages=[
            {"role": "user", "content": "I prefer Postgres over Mongo for relational data."},
        ],
    )

    # Recall
    ctx = m.context(
        user_id=user_id,
        organization_id="<your organization id>",
        session_id=session_id,
        token_budget=1500,
    )

    # Use in any LLM call
    system_prompt = ctx.to_system_prompt()
```

`Contexta` and `AsyncContexta` are the canonical class names. The historical
lowercase `contexta` / `Asynccontexta` still import and work, but emit a
`DeprecationWarning` and will be removed in a future major release.

## Documentation

Full docs at [docs.contexta.dev](https://docs.contexta.dev).

## Configuration

| Env var | Default | Description |
|---|---|---|
| `CONTEXTA_API_KEY` | — | Required. Your API key. |
| `CONTEXTA_API_URL` | `https://api.contexta.dev/v1` | Base URL for the API. |
| `CONTEXTA_ORGANIZATION_ID` | — | Required by `context()` and `create_session()`. |
| `CONTEXTA_TIMEOUT_MS` | `30000` | Request timeout. |
| `CONTEXTA_MAX_RETRIES` | `3` | Max retries on failures. |
| `CONTEXTA_TELEMETRY` | `true` | Set `false` to disable telemetry. |
| `CONTEXTA_VERIFY_TLS` | `true` | Set `false` to disable certificate verification. |
| `CONTEXTA_CA_BUNDLE` | — | Path to a PEM CA bundle, e.g. the local gateway cert. |

## TLS

Certificate verification is on by default. To trust the self-signed local
gateway, point the client at its certificate authority:

```python
m = Contexta.from_env()  # or Contexta(ca_bundle_path="./certs/gateway-ca.pem")
m = Contexta(api_key=..., ca_bundle_path="./certs/gateway-ca.pem")
```

Disabling verification is an explicit opt-in and never happens implicitly:

```python
m = Contexta(api_key=..., verify_tls=False)  # local development only
```

## Durability

Every write carries an `Idempotency-Key`, retries 429/5xx/network failures with
backoff, and falls back to an on-disk queue (`~/.contexta/buffer.jsonl`) when the
network is down.

```python
m.flush()  # force the offline queue to drain; returns entries replayed
m.close()  # release connections; safe to call twice
```

Use the client as a context manager to get both automatically.

## Error handling

```python
from contexta_client import Contexta, AuthenticationError, QuotaExceeded

m = Contexta.from_env()
try:
    m.observe(user_id="u_123", messages=[{"role": "user", "content": "Hi"}])
except AuthenticationError:
    print("Check your API key")
except QuotaExceeded:
    print("Upgrade your plan")
```

## Async support

```python
from contexta_client import AsyncContexta

am = AsyncContexta.from_env()

async def handle_turn():
    async with am:
        ctx = await am.context(
            user_id=user_id,
            organization_id=organization_id,
            session_id=session_id,
            token_budget=1500,
        )
        return ctx.to_system_prompt()
```

## Adapters

```python
from contexta_client.adapters.openai import contextaMemory, contextaAssistantRunner
from contexta_client.adapters.anthropic import contextaMemory, contextaChat
from contexta_client.adapters.langchain import contextaChatHistory
from contexta_client.adapters.llamaindex import contextaChatMemory
```

Each adapter takes the client plus a `user_id` because `GET /v1/memories/context`
requires `user_id`, `organization_id` and `session_id`:

```python
memory = contextaMemory(m, user_id=user_id, token_budget=2000)
```

## License

MIT
