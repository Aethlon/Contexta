# Quickstart — 5 Minutes to First Memory

Get contexta running in your agent in under five minutes.

## 1. Install the SDK

**Python:**
```bash
pip install contexta-client
```

**TypeScript:**
```bash
npm install @contexta/client
```

## 2. Get an API Key

1. Go to [app.contexta.dev](https://app.contexta.dev) and sign in.
2. Create a new project.
3. Generate an API key with default scopes (`observations:write`, `retrieval:read`, `memories:read`).
4. Copy the key — it's shown once.

Set it in your environment:

```bash
export CONTEXTA_API_KEY=mk_live_your_key_here
```

## 3. Send Your First Observation

```python
from contexta_client import contexta

contexta = contexta.from_env()

contexta.observe(
    user_id="user_001",
    messages=[
        {"role": "user", "content": "I prefer Postgres over Mongo for relational data."},
        {"role": "assistant", "content": "Got it, I'll keep that in mind."},
    ],
)
```

```ts
import { contexta } from "@contexta/client";

const contexta = contexta.fromEnv();

await contexta.observe({
  userId: "user_001",
  messages: [
    { role: "user", content: "I prefer Postgres over Mongo for relational data." },
    { role: "assistant", content: "Got it, I'll keep that in mind." },
  ],
});
```

The observation is accepted asynchronously. Extraction runs in the background.

## 4. Retrieve Context

After a few seconds, ask contexta to recall:

```python
ctx = contexta.context(
    user_id="user_001",
    query="what database does the user prefer?",
    token_budget=1500,
)

print(ctx.to_system_prompt())
# ─ Preferences ─
# - User prefers Postgres over Mongo for relational data.
```

```ts
const ctx = await contexta.context({
  userId: "user_001",
  query: "what database does the user prefer?",
  tokenBudget: 1500,
});

console.log(ctx.toSystemPrompt());
```

## 5. Complete Loop

Here's the full agent loop:

```python
from contexta_client import contexta
from openai import OpenAI

contexta = contexta.from_env()
openai = OpenAI()

def chat(user_message: str, user_id: str, session_id: str) -> str:
    # 1. Fetch context
    ctx = contexta.context(user_id=user_id, session_id=session_id, query=user_message)
    
    # 2. Call LLM with context
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": ctx.to_system_prompt()},
            {"role": "user", "content": user_message},
        ],
    )
    reply = response.choices[0].message.content
    
    # 3. Observe the turn
    contexta.observe(
        user_id=user_id,
        session_id=session_id,
        messages=[
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": reply},
        ],
    )
    return reply
```

That's it. Three SDK calls per turn: `context()`, LLM, `observe()`.

Next: [Concepts overview](/concepts).
