"""LLM service abstraction for the contexta memory engine.

Provides a unified interface for calling LLM providers (OpenAI, DeepSeek, etc.)
for memory extraction, classification, and other intelligence tasks.
All OpenAI-compatible APIs are supported via the llm_base_url setting.
"""

import json
import logging
from typing import Any, Protocol

from contexta.config.settings import Settings, get_settings
from contexta.core.types import EXCLUDED_ENTITY_WORDS

logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    """Protocol for LLM provider implementations."""

    async def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate a completion from the LLM.

        Args:
            prompt: The user prompt to send.
            system_prompt: Optional system prompt for context.

        Returns:
            The LLM response text.
        """
        ...

    async def complete_json(
        self, prompt: str, system_prompt: str | None = None
    ) -> dict[str, Any]:
        """Generate a JSON-structured completion from the LLM.

        Args:
            prompt: The user prompt to send.
            system_prompt: Optional system prompt for context.

        Returns:
            Parsed JSON response from the LLM.

        Raises:
            LLMError: If the response cannot be parsed as JSON.
        """
        ...


class LLMError(Exception):
    """Raised when an LLM operation fails."""

    def __init__(self, message: str = "LLM operation failed.") -> None:
        self.message = message
        super().__init__(self.message)


class LLMService:
    """Service for interacting with LLM providers.

    Wraps provider-specific logic and provides a clean interface
    for memory extraction and classification tasks.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate a text completion from the configured LLM provider.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system-level instructions.

        Returns:
            The LLM response text.

        Raises:
            LLMError: If the LLM call fails.
        """
        try:
            return await self._call_provider(prompt, system_prompt)
        except Exception as exc:
            logger.error("LLM completion failed: %s", exc)
            raise LLMError(f"LLM completion failed: {exc}") from exc

    async def complete_json(
        self, prompt: str, system_prompt: str | None = None
    ) -> dict[str, Any]:
        """Generate a JSON-structured completion from the configured LLM provider.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system-level instructions.

        Returns:
            Parsed JSON dict from the LLM response.

        Raises:
            LLMError: If the call fails or response is not valid JSON.
        """
        response = await self.complete(prompt, system_prompt)
        try:
            # Strip markdown code fences if present
            cleaned = response.strip()
            cleaned = cleaned.removeprefix("```json")
            cleaned = cleaned.removeprefix("```")
            cleaned = cleaned.removesuffix("```")
            return json.loads(cleaned.strip())
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Failed to parse LLM JSON response: %s", exc)
            raise LLMError(f"Failed to parse LLM JSON response: {exc}") from exc

    async def _call_provider(self, prompt: str, system_prompt: str | None) -> str:
        """Call the configured LLM provider.

        This method dispatches to the appropriate provider based on settings.
        Currently supports OpenAI-compatible APIs.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt.

        Returns:
            Raw response text from the provider.
        """
        provider = self._settings.llm_provider

        # Enforce offline mode strictly when set
        if self._settings.engine_mode == "offline" or provider in ("local", "offline", "qwen"):
            return await self._call_local_model_server(prompt, system_prompt)
        elif provider in ("openai", "deepseek"):
            try:
                return await self._call_openai_compatible(prompt, system_prompt)
            except Exception as exc:
                logger.warning("Cloud LLM provider failed (%s); falling back to local model server.", exc)
                return await self._call_local_model_server(prompt, system_prompt)
        else:
            raise LLMError(f"Unsupported LLM provider: {provider}")

    async def _call_local_model_server(self, prompt: str, system_prompt: str | None) -> str:
        """Execute local model server inference for structured extraction, classification, and scoring."""
        import httpx

        url = getattr(self._settings, "local_model_server_url", "http://localhost:8001")

        # Parse observation messages if prompt is an ExtractionWorker payload
        parsed_messages: list[dict] = []
        try:
            payload_data = json.loads(prompt)
            if isinstance(payload_data, dict) and "messages" in payload_data:
                parsed_messages = [m for m in payload_data["messages"] if isinstance(m, dict) and m.get("text")]
        except Exception:
            pass

        texts_to_classify = [m["text"] for m in parsed_messages] if parsed_messages else [prompt[:500]]
        predictions: list[dict] = []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{url}/v1/classify",
                    json={"texts": texts_to_classify[:50], "labels": ["preference", "fact", "goal", "event", "other"]},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    predictions = data.get("predictions", [])
        except Exception as exc:
            logger.warning("Local model server classify call failed (%s); using heuristic fallback.", exc)

        import re
        memories_out: list[dict] = []
        for idx, text in enumerate(texts_to_classify):
            pred_label = predictions[idx]["label"] if idx < len(predictions) else "fact"
            speaker = parsed_messages[idx].get("speaker", "Speaker") if idx < len(parsed_messages) else "User"

            clean_text = re.sub(r"\[Date:[^\]]+\]", "", text)
            # 1. Proper nouns / capitalized entities
            caps = re.findall(r"\b[A-Z][a-z]{1,}(?:\s+[A-Z][a-z]{1,})*\b", clean_text)
            entities_set = {
                c.strip() for c in caps
                if c.lower() not in EXCLUDED_ENTITY_WORDS and len(c.strip()) > 2
            }
            if speaker and len(speaker) > 2 and speaker.lower() not in EXCLUDED_ENTITY_WORDS:
                entities_set.add(speaker)
            found_entities = list(entities_set)
            memories_out.append({
                "title": f"{speaker}: {text[:50].strip()}",
                "content": f"{speaker}: {text.strip()}",
                "memory_type": pred_label,
                "source_type": "user_explicit",
                "entities": found_entities,
            })

        first_label = predictions[0]["label"] if predictions else "fact"
        first_score = predictions[0]["score"] if predictions else 0.85
        structured = {
            "memories": memories_out or [{
                "title": prompt[:50],
                "content": prompt[:200],
                "memory_type": "fact",
                "source_type": "user_explicit",
                "entities": [],
            }],
            "facts": [{"statement": prompt[:200], "category": first_label, "confidence": first_score}],
            "entities": [],
            "memory_type": first_label,
        }
        return json.dumps(structured)

    async def _call_openai_compatible(self, prompt: str, system_prompt: str | None) -> str:
        """Call any OpenAI-compatible API (OpenAI, DeepSeek, etc.).

        Uses httpx for async HTTP calls to avoid heavy SDK dependency.
        """
        import httpx

        api_key = self._settings.llm_api_key
        model = self._settings.llm_model
        base_url = self._settings.llm_base_url

        if not api_key:
            logger.info("LLM API key missing (CONTEXTA_LLM_API_KEY). Using local model server fallback.")
            return await self._call_local_model_server(prompt, system_prompt)

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        body: dict = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
        }
        if self._settings.llm_provider == "openai":
            body["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
