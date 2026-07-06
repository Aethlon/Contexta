"""LLM service abstraction for the contexta memory engine.

Provides a unified interface for calling LLM providers (OpenAI, DeepSeek, etc.)
for memory extraction, classification, and other intelligence tasks.
All OpenAI-compatible APIs are supported via the llm_base_url setting.
"""

import json
import logging
from typing import Any, Protocol

from contexta.config.settings import Settings, get_settings

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
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
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

        if provider in ("openai", "deepseek"):
            return await self._call_openai_compatible(prompt, system_prompt)
        else:
            raise LLMError(f"Unsupported LLM provider: {provider}")

    async def _call_openai_compatible(self, prompt: str, system_prompt: str | None) -> str:
        """Call any OpenAI-compatible API (OpenAI, DeepSeek, etc.).

        Uses httpx for async HTTP calls to avoid heavy SDK dependency.
        """
        import httpx

        api_key = self._settings.llm_api_key
        model = self._settings.llm_model
        base_url = self._settings.llm_base_url

        if not api_key:
            raise LLMError("LLM API key not configured (CONTEXTA_LLM_API_KEY)")

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
