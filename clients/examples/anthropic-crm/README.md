# Anthropic CRM Agent with contexta Memory

A CRM assistant powered by Claude that remembers customer preferences, deal stages, and interaction history using contexta.

## Features

- Persistent customer context across conversations
- `contextaChat` helper with auto-flush on assistant turn boundaries
- Tracks contact details, deal stages, and customer sentiment
- `context_for()` injects relevant CRM data before each Claude call

## Five-Minute Quickstart

```bash
pip install contexta-anthropic contexta-client anthropic

export CONTEXTA_API_KEY="your-contexta-api-key"
export CONTEXTA_BASE_URL="https://api.contexta.ai/v1"
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

```python
import os
from contexta_client import contexta
from contexta_client.adapters.anthropic import contextaMemory, contextaChat
from anthropic import Anthropic

contexta = contexta(api_key=os.environ["CONTEXTA_API_KEY"])
anthropic = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
session_id = "crm-demo-acme-corp"

memory = contextaMemory(contexta, token_budget=2000)
chat = contextaChat(contexta, session_id=session_id, memory=memory)

# Fetch context before the conversation
ctx = chat.get_context()
system_prompt = "\n".join(f"{b['content']}" for b in ctx)

response = anthropic.messages.create(
    model="claude-sonnet-4-20250514",
    system=system_prompt or "You are a CRM assistant.",
    messages=[{"role": "user", "content": "Summarize our dealings with Acme Corp."}],
    max_tokens=1024,
)

chat.turn("user", "Summarize our dealings with Acme Corp.")
chat.turn("assistant", response.content[0].text)
```

Claude now remembers everything about Acme Corp across sessions.
