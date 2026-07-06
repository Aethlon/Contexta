# OpenAI Coding Agent with contexta Memory

A coding assistant agent that remembers your tech preferences across sessions using contexta's memory engine and the OpenAI Assistants API.

## Features

- Remembers your preferred programming languages, frameworks, and tools
- Injects relevant context before each interaction via `[contexta Context]` system messages
- Observes every conversation turn to build a persistent user model
- Thread ID ↔ Session ID mapping keeps conversations isolated

## Five-Minute Quickstart

```bash
# 1. Install dependencies
pip install contexta-openai contexta-client openai

# 2. Set credentials
export CONTEXTA_API_KEY="your-contexta-api-key"
export CONTEXTA_BASE_URL="https://api.contexta.ai/v1"
export OPENAI_API_KEY="your-openai-api-key"

# 3. Create and run the agent
cat <<EOF > agent.py
import os
from contexta_client import contexta
from contexta_client.adapters.openai import contextaMemory, contextaAssistantRunner
from openai import OpenAI

contexta = contexta(api_key=os.environ["CONTEXTA_API_KEY"])
openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
memory = contextaMemory(contexta, token_budget=2000)
runner = contextaAssistantRunner(openai_client, memory)

session_id = "coding-agent-demo-1"

# Create an assistant first with an appropriate coding instruction
# assistant = openai_client.beta.assistants.create(
#     name="Coding Buddy",
#     instructions="You are a helpful coding assistant.",
#     model="gpt-4o",
# )

response = runner.run_with_session(
    assistant_id="asst_YOUR_ASSISTANT_ID",
    session_id=session_id,
    user_message="I prefer Python and FastAPI for backend development.",
)
print(f"Run status: {response.status}")
EOF
python agent.py
```

Now ask it anything — it will remember your preferences from this and future sessions.
