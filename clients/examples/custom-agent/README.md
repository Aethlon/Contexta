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
export CONTEXTA_ORGANIZATION_ID="your-organization-id"
export OPENAI_API_KEY="your-openai-api-key"
```

```python
import os
from uuid import uuid4

from contexta_client import Contexta
from openai import OpenAI

client = Contexta(api_key=os.environ["CONTEXTA_API_KEY"])
openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
user_id = str(uuid4())
organization_id = os.environ["CONTEXTA_ORGANIZATION_ID"]
session_id = str(uuid4())

def chat(message: str) -> str:
    # 1. Fetch contexta context
    ctx = client.context(
        user_id=user_id,
        organization_id=organization_id,
        session_id=session_id,
        token_budget=1500,
    )
    context_parts = []
    if ctx.user_profile:
        context_parts.append(f"User: {ctx.user_profile}")
    for pref in ctx.preferences:
        context_parts.append(f"Preference: {pref}")
    for mem in ctx.relevant_memories:
        context_parts.append(f"[Memory] {mem}")

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
    client.observe(
        user_id=user_id,
        session_id=session_id,
        messages=[
            {"role": "user", "content": message},
            {"role": "assistant", "content": reply},
        ],
    )
    return reply

try:
    print(chat("Hi! I'm building a web app with Next.js."))
    print(chat("What do you remember about me?"))
finally:
    client.close()
```

Run the script multiple times — the agent builds a persistent memory of you.
