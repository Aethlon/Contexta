# 10 — Integrations

This document covers how contexta plugs into popular agent frameworks and runtimes. The two launch-week integrations are **OpenAI Assistants** and **LlamaIndex**. After that: **Anthropic Claude**, **LangChain**, and **custom agent loops**.

## Decisions of record

1. **Each integration is a thin adapter** that calls contexta via the official SDK. We do not fork or vendor the framework code.
2. **Adapters live in their own packages** so customers install only what they need:
   - `contexta-openai` (Pip), `@contexta/openai` (npm)
   - `contexta-llamaindex`
   - `contexta-anthropic` / `@contexta/anthropic`
   - `contexta-langchain` / `@contexta/langchain`
3. **Every adapter ships a "Five-Minute Quickstart"** that takes a customer from `pip install` to first retrieval in under 5 minutes.
4. **Adapters are open-source** (MIT) — the engine is closed source, but adapter code is thin glue and we want frameworks to vendor or recommend us.

## Integration matrix

| Framework | Pip pkg | npm pkg | Quickstart | Status |
|---|---|---|---|---|
| OpenAI Assistants | `contexta-openai` | `@contexta/openai` | docs/openai-assistants.md | Sprint 8 |
| LlamaIndex | `contexta-llamaindex` | n/a (Python only) | docs/llamaindex.md | Sprint 9 |
| Anthropic Claude | `contexta-anthropic` | `@contexta/anthropic` | docs/anthropic.md | Sprint 10 |
| LangChain | `contexta-langchain` | `@contexta/langchain` | docs/langchain.md | Sprint 11 |
| Vercel AI SDK | n/a | `@contexta/vercel-ai` | docs/vercel-ai.md | Sprint 11 |
| Generic / Custom loop | (uses base SDK) | (uses base SDK) | docs/custom-agent.md | Sprint 8 |

## OpenAI Assistants integration

The Assistants API has its own thread-and-message model. contexta sits alongside as the long-term memory layer that survives across threads.

**Pattern: hook into thread events**.

```python
from openai import OpenAI
from CONTEXTA_openai import contextaMemory
from contexta_client import contexta

openai_client = OpenAI()
contexta = contexta.from_env()
memory = contextaMemory(contexta, openai_client)

# Before sending user message, fetch context
context = memory.context_for(user_id="u_123", query=user_message, token_budget=1500)

# Inject context as a system message preamble
thread = openai_client.beta.threads.create(messages=[
    {"role": "user", "content": user_message},
])

run = openai_client.beta.threads.runs.create(
    thread_id=thread.id,
    assistant_id=ASSISTANT_ID,
    additional_instructions=context.to_system_prompt(),
)

# Wait for run to complete...

# After run completes, observe the conversation
messages = openai_client.beta.threads.messages.list(thread_id=thread.id)
memory.observe_thread(user_id="u_123", session_id=thread.id, messages=messages)
```

The adapter handles:
- Translating OpenAI messages to contexta's observation shape.
- Token-budget respect when injecting context as system instructions.
- Stable mapping from OpenAI thread ID to contexta session ID.
- Auto-batching observations to avoid one POST per message.
- Propagating user_id from a customer-supplied function (we don't try to extract it from OpenAI).

### Drop-in helpers

```python
# Even simpler: a single class that wraps the run lifecycle
from CONTEXTA_openai import contextaAssistantRunner

runner = contextaAssistantRunner(
    openai=openai_client,
    contexta=contexta,
    assistant_id=ASSISTANT_ID,
    user_id_resolver=lambda thread_id: lookup_user(thread_id),
)

result = runner.run(thread_id=thread.id, message=user_message)
# Memory context is auto-injected; observations are auto-emitted post-run.
```


## LlamaIndex integration

LlamaIndex has a `Memory` interface (`ChatMemoryBuffer`, `VectorMemory`, etc.). We implement `contextaChatMemory` that conforms to LlamaIndex's `BaseMemory` protocol.

```python
from llama_index.core.agent import ReActAgent
from llama_index.core.tools import FunctionTool
from CONTEXTA_llamaindex import contextaChatMemory

memory = contextaChatMemory.from_env(
    user_id="u_123",
    session_id="s_456",
    token_budget=1500,
)

agent = ReActAgent.from_tools(
    tools=[some_tool],
    llm=llm,
    memory=memory,
    verbose=True,
)

response = agent.chat("What database did I say I prefer?")
# memory.get_all() returns contexta-fetched messages + retrieved memories
# memory.put(message) emits a contexta observation
```

The adapter exposes contexta as a drop-in replacement for `ChatMemoryBuffer`. Underneath:
- `get_all()` calls `contexta.context()` and returns a list of `ChatMessage` synthesized from the context bundle.
- `put(message)` buffers messages and emits a single observation when the buffer reaches a turn boundary or N messages.
- Token budget is honored: LlamaIndex passes its budget; we pass it through to contexta.

LlamaIndex also has `VectorMemory`. We do not replace that — contexta is layered on top, not underneath. Customers can use LlamaIndex's vector store for document RAG and contexta for conversational memory simultaneously.

## Anthropic Claude integration

Claude doesn't have an Assistants API yet (as of May 2026). The integration pattern is direct:

```python
from anthropic import Anthropic
from CONTEXTA_anthropic import contextaMemory

claude = Anthropic()
memory = contextaMemory.from_env()

context = memory.context_for(user_id="u_123", query=user_message, token_budget=1500)

response = claude.messages.create(
    model="claude-3-7-sonnet",
    system=context.to_system_prompt(),
    messages=[{"role": "user", "content": user_message}],
    max_tokens=1024,
)

memory.observe(
    user_id="u_123",
    session_id="s_456",
    messages=[
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": response.content[0].text},
    ],
)
```

Because Anthropic doesn't manage threads, the customer passes their own `session_id`. The adapter offers a `contextaChat` helper that maintains an in-memory message buffer and flushes on turn boundaries, mirroring the OpenAI helper.

## LangChain integration

LangChain has a deprecated `Memory` API and a newer `BaseChatMessageHistory` for LCEL. We implement both for backward compat, but recommend LCEL.

```python
from langchain.schema import AIMessage, HumanMessage
from CONTEXTA_langchain import contextaChatHistory

history = contextaChatHistory(
    user_id="u_123",
    session_id="s_456",
)

# In an LCEL chain
chain = (
    ChatPromptTemplate.from_messages([
        ("system", "{CONTEXTA_context}"),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ])
    | llm
    | StrOutputParser()
)

with_history = RunnableWithMessageHistory(
    chain,
    lambda session_id: contextaChatHistory(user_id=session_id),
    input_messages_key="input",
    history_messages_key="history",
)

result = with_history.invoke(
    {"input": "What database do I prefer?", "CONTEXTA_context": context.to_system_prompt()},
    config={"configurable": {"session_id": "u_123"}},
)
```

## Vercel AI SDK integration

For the JS/TS audience. The Vercel AI SDK uses `experimental_streamData` and a tool-calling pattern. We hook into `onFinish`.

```ts
import { openai } from "@ai-sdk/openai";
import { streamText } from "ai";
import { contextaMemory } from "@contexta/vercel-ai";

const memory = contextaMemory({
  apiKey: process.env.CONTEXTA_API_KEY!,
  userId: "u_123",
  sessionId: "s_456",
});

const result = await streamText({
  model: openai("gpt-4o-mini"),
  system: await memory.contextFor(userPrompt, 1500),
  messages: [{ role: "user", content: userPrompt }],
  onFinish: async ({ text }) => {
    await memory.observe([
      { role: "user", content: userPrompt },
      { role: "assistant", content: text },
    ]);
  },
});
```

## Custom agent loop (no framework)

For customers who write their own loop, the documentation focuses on three calls:

```python
from contexta_client import contexta

contexta = contexta.from_env()

# 1. Fetch context before generation
context = contexta.context(
    user_id=current_user_id,
    session_id=current_session_id,
    query=latest_user_message,
    token_budget=1500,
)

# 2. Pass context.to_system_prompt() (or context.relevant_memories) into the LLM call

# 3. After the assistant responds, observe both messages
contexta.observe(
    user_id=current_user_id,
    session_id=current_session_id,
    messages=[
        {"role": "user", "content": latest_user_message},
        {"role": "assistant", "content": assistant_response},
    ],
)
```

That's the full integration surface. Three calls. Documented prominently in the docs site at /custom-agent.

## SDK-level conveniences shared across adapters

All adapters share these helpers from the base SDK:

```python
class Context:
    user_profile: UserProfile | None
    active_projects: list[Project]
    preferences: list[Preference]
    goals: list[Goal]
    recent_events: list[Event]
    relevant_memories: list[ScoredMemory]
    token_usage: TokenUsage

    def to_system_prompt(self) -> str:
        """Render context as a structured system prompt block."""
    def to_messages(self) -> list[Message]:
        """Render context as a list of role/content pairs."""
    def to_markdown(self) -> str:
        """Render context as markdown for debugging."""
```

The default `to_system_prompt()` formatting is:

```
contexta Memory:
─ User profile ─
{user_profile}

─ Active projects ─
{active_projects}

─ Preferences ─
{preferences}

─ Goals ─
{goals}

─ Recent events ─
{recent_events}

─ Relevant context ─
{relevant_memories}
```

Customers can override formatting per integration via `Context.format(template=...)`.

## What we explicitly do not integrate with

- **Vector databases** (Pinecone, Weaviate, Qdrant, Chroma). We are the layer above; customers can keep those for document RAG.
- **Conversation logging tools** (LangSmith, Helicone). Different category. contexta focuses on memory, those focus on observability.
- **Voice agents** (Vapi, Retell). Adapter pattern fits but not until customer demand.
- **Other memory products** (Mem0, Letta, Zep). Direct competitors, no integration.

## Test fixture: the "wow demo" agent

Every integration ships with a runnable example in `examples/`:

- `examples/openai-coding-agent/` — a coding-policy agent that remembers tech preferences across sessions.
- `examples/llamaindex-tutor/` — a tutor agent that tracks weak topics.
- `examples/anthropic-crm/` — a CRM agent that tracks contacts and deal stages.

Each example has a README that runs in <5 minutes and a screen recording of the "wow moment" (agent recalling user context across sessions).
