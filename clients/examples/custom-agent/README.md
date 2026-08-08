# Custom Agent Loop with contexta Base SDK

A minimal example showing how to build a custom agent loop using only the contexta base SDK — no framework adapter needed.

## Features

- Direct `contexta.context()` and `contexta.observe()` calls
- Manual context injection into any LLM call
- Full control over the agent loop
- Demonstrates session management and observation batching

## Five-Minute Quickstart

```bash
pip install contexta-client openai

export CONTEXTA_API_KEY="your-contexta-api-key"
export CONTEXTA_BASE_URL="https://api.contexta.ai/v1"
export OPENAI_API_KEY="your-openai-api-key"
```

```python
import os
from contexta_client import contexta
from openai import OpenAI

contexta = contexta(api_key=os.environ["CONTEXTA_API_KEY"])
openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
session_id = "custom-agent-demo-1"

def chat(message: str) -> str:
    # 1. Fetch contexta context
    ctx = contexta.context(session_id=session_id, token_budget=1500)
    context_parts = []
    if ctx.user_profile:
        context_parts.append(f"User: {ctx.user_profile.name}")
    for pref in ctx.preferences:
        context_parts.append(f"Preference: {pref.category}={pref.value}")
    for mem in ctx.relevant_memories:
        context_parts.append(f"[Memory] {mem.title}: {mem.content}")

    # 2. Call LLM with context injected as system message
    system = "\n".join(context_parts) or "You are a helpful assistant."
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ],
    )
    reply = response.choices[0].message.content

    # 3. Observe the turn
    contexta.observe(
        session_id=session_id,
        messages=[
            {"role": "user", "content": message},
            {"role": "assistant", "content": reply},
        ],
    )
    return reply

print(chat("Hi! I'm building a web app with Next.js."))
print(chat("What do you remember about me?"))
```

Run the script multiple times — the agent builds a persistent memory of you.
