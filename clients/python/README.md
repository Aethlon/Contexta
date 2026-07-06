# contexta Python SDK

Persistent memory layer for AI agents. Built for agent developers who need their agents to remember user preferences, facts, and context across sessions.

## Installation

```bash
pip install contexta-client
```

## Quick start

```python
from contexta_client import contexta

m = contexta.from_env()  # reads CONTEXTA_API_KEY

# Remember
m.observe(
    user_id="u_123",
    messages=[
        {"role": "user", "content": "I prefer Postgres over Mongo for relational data."},
    ],
)

# Recall
ctx = m.context(user_id="u_123", token_budget=1500)

# Use in any LLM call
system_prompt = ctx.to_system_prompt()
```

## Documentation

Full docs at [docs.contexta.dev](https://docs.contexta.dev).

## Configuration

| Env var | Default | Description |
|---|---|---|
| `CONTEXTA_API_KEY` | — | Required. Your API key. |
| `CONTEXTA_API_URL` | `https://api.contexta.dev/v1` | Base URL for the API. |
| `CONTEXTA_TIMEOUT_MS` | `30000` | Request timeout. |
| `CONTEXTA_MAX_RETRIES` | `3` | Max retries on failures. |
| `CONTEXTA_TELEMETRY` | `true` | Set `false` to disable telemetry. |

## CLI

```bash
contexta --help
contexta login
contexta init
contexta test
contexta observations send --user-id u_123 --file observation.json
contexta context get --user-id u_123
contexta usage
```

## Error handling

```python
from contexta_client import contexta, AuthenticationError, QuotaExceeded

m = contexta.from_env()
try:
    m.observe(user_id="u_123", messages=[{"role": "user", "content": "Hi"}])
except AuthenticationError:
    print("Check your API key")
except QuotaExceeded:
    print("Upgrade your plan")
```

## Async support

```python
from contexta_client import Asynccontexta

am = Asynccontexta.from_env()

async def handle_turn():
    ctx = await am.context(user_id="u_123", token_budget=1500)
    return ctx.to_system_prompt()
```

## Adapters

```python
from contexta_client.adapters.openai import OpenAIMiddleware
from contexta_client.adapters.langchain import contextaMemory
from contexta_client.adapters.llamaindex import contextaChatMemory
from contexta_client.adapters.anthropic import AnthropicMiddleware
```

## License

MIT
