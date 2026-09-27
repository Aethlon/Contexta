# LlamaIndex Tutor with contexta Memory

A tutor agent built with LlamaIndex that remembers what topics you've covered and your learning preferences using contexta.

## Features

- Drop-in `contextaChatMemory` replacing `ChatMemoryBuffer`
- Tracks learning progress and topic mastery across sessions
- Context-aware tutoring that builds on previously covered material
- Token-budget-aware context assembly via contexta's planner

## Five-Minute Quickstart

```bash
pip install contexta-llamaindex contexta-client llama-index-core

export CONTEXTA_API_KEY="your-contexta-api-key"
export CONTEXTA_BASE_URL="https://api.contexta.ai/v1"
export CONTEXTA_ORGANIZATION_ID="your-organization-id"
export OPENAI_API_KEY="your-openai-api-key"
```

```python
import os
from uuid import uuid4

from contexta_client import Contexta
from contexta_client.adapters.llamaindex import contextaChatMemory
from llama_index.core import Document, VectorStoreIndex
from llama_index.core.memory import ChatMemoryBuffer

client = Contexta(api_key=os.environ["CONTEXTA_API_KEY"])
user_id = "tutor-demo-1"
session_id = str(uuid4())

memory = contextaChatMemory(
    client=client,
    user_id=user_id,
    session_id=session_id,
    token_budget=2000,
)

# Index some documents
docs = [Document(text="Python uses indentation for blocks.")]
index = VectorStoreIndex.from_documents(docs)

chat_engine = index.as_chat_engine(
    chat_mode="context",
    memory=memory,
    llm=...,
)

response = chat_engine.chat("What's unique about Python syntax?")
print(response)

memory.flush()  # persist observations to contexta
client.close()
```

Run it again and the tutor will recall your past questions.
