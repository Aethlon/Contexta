"""LLM service abstraction for the contexta memory engine.

Provides a unified interface for calling LLM providers (OpenAI, DeepSeek, etc.)
for memory extraction, classification, and other intelligence tasks.
All OpenAI-compatible APIs are supported via the llm_base_url setting.
"""

import asyncio
import json
import logging
import re
from typing import Any, Protocol

from contexta.config.settings import Settings, get_settings
from contexta.core.types import EXCLUDED_ENTITY_WORDS, MemoryType

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^\s*```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\r?\n(.*?)\r?\n?\s*```\s*$", re.DOTALL)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_ORPHAN_FENCE_RE = re.compile(r"```[ \t]*[A-Za-z0-9_+-]*[ \t]*\r?\n?", re.IGNORECASE)


def _balanced_json_slice(text: str) -> str | None:
    """Return the first balanced {...} or [...] span, ignoring braces in strings."""
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
    return None


def extract_json_block(response: str) -> str:
    """Reduce a chat completion to the JSON payload it contains.

    Small instruct models routinely wrap JSON in a markdown fence, prepend a
    sentence of preamble, or emit a reasoning block first, so a bare
    ``json.loads(response)`` fails on output that is semantically valid. Each
    stage below is a strictly wider net than the last.
    """
    text = _THINK_RE.sub("", str(response or "")).strip()
    if not text:
        return text

    fenced = _FENCE_RE.match(text)
    if fenced:
        text = fenced.group(2).strip()

    text = _ORPHAN_FENCE_RE.sub("", text).strip()

    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    candidate = _balanced_json_slice(text)
    if candidate is not None:
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    return text


def normalize_memory_type_label(value: Any) -> str:
    label = str(value or "").strip().lower()
    aliases = {"other": "custom", "unknown": "custom", "memory": "custom"}
    label = aliases.get(label, label)
    valid = {memory_type.value for memory_type in MemoryType}
    return label if label in valid else MemoryType.CUSTOM.value


def infer_memory_type(text: str) -> str:
    value = text.lower()
    if re.search(r"\b(prefer|prefers|preferred|favorite|favourite|love|loves|likes)\b", value):
        return MemoryType.PREFERENCE.value
    if re.search(r"\b(goal|plan|planning|intend|intends|want to|going to|will)\b", value):
        return MemoryType.GOAL.value
    if re.search(r"\b(friend|brother|sister|mother|father|wife|husband|partner|relationship)\b", value):
        return MemoryType.RELATIONSHIP.value
    if re.search(r"\b(learn\w*|know\w*|can|skill\w*|practic\w*|experienc\w*|studying|training)\b", value):
        return MemoryType.SKILL.value
    if re.search(r"\b(yesterday|today|last|next|went|joined|attended|bought|sold|met|visited|started|finished)\b", value):
        return MemoryType.EVENT.value
    return MemoryType.FACT.value


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

    #: Re-ask budget for a malformed JSON body. A dropped comma is a sampling
    #: accident far more often than it is an impossible prompt.
    JSON_MAX_ATTEMPTS = 3

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _is_ollama(self) -> bool:
        provider = str(getattr(self._settings, "llm_provider", "") or "").casefold()
        base_url = str(getattr(self._settings, "llm_base_url", "") or "").casefold()
        return "11434" in base_url or provider == "ollama"

    def _json_mode_body(self, json_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        """Request schema-constrained decoding where the provider supports it.

        Without this the model free-forms its answer and small local models
        routinely emit an unparseable body. Ollama spells the hint `format` and
        accepts a full JSON Schema, which is strictly stronger than asking for
        bare `json`: the sampler can then only emit a conforming document.
        OpenAI spells it `response_format`. Sending the wrong one is an error on
        some providers, so each is sent only to a provider known to accept it.
        """
        provider = str(getattr(self._settings, "llm_provider", "") or "").casefold()
        if provider == "openai":
            return {"response_format": {"type": "json_object"}}
        if self._is_ollama():
            return {"format": json_schema if json_schema else "json"}
        return {}

    async def _call_ollama(
        self,
        prompt: str,
        system_prompt: str | None,
        *,
        temperature: float | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        """Call Ollama's native chat endpoint.

        Deliberately NOT the OpenAI-compatible `/v1/chat/completions` route:
        that endpoint silently DROPS the `format` field, so a schema constraint
        is ignored and the model answers in prose. Verified against a live
        server -- the same request returns conforming JSON on `/api/chat` and
        the text "Certainly." on `/v1/chat/completions`.
        """
        import httpx

        base_url = str(self._settings.llm_base_url or "http://localhost:11434").rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[: -len("/v1")]
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": self._settings.llm_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1 if temperature is None else temperature},
        }
        body.update(self._json_mode_body(json_schema))

        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(f"{base_url}/api/chat", json=body)
            if response.status_code >= 400:
                raise LLMError(
                    f"Ollama returned {response.status_code}: {response.text[:500]}"
                )
            data = response.json()
            return str((data.get("message") or {}).get("content", "")).strip()

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        *,
        temperature: float | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        """Generate a text completion from the configured LLM provider.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system-level instructions.
            temperature: Overrides the configured sampling temperature. `complete_json`
                uses this on retries so a repeat attempt does not deterministically
                reproduce the same malformed token sequence.

        Returns:
            The LLM response text.

        Raises:
            LLMError: If the LLM call fails.
        """
        try:
            return await self._call_provider(
            prompt, system_prompt, temperature=temperature, json_schema=json_schema
        )
        except Exception as exc:
            logger.error("LLM completion failed: %s", exc)
            raise LLMError(f"LLM completion failed: {exc}") from exc

    async def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        *,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a JSON-structured completion from the configured LLM provider.

        Retries a bounded number of times. A malformed body is usually a
        sampling accident rather than a hopeless prompt, and re-asking is
        non-destructive -- unlike repairing the text, which would risk storing
        silently corrupted facts.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system-level instructions.
            json_schema: Optional JSON Schema for providers that support
                grammar-constrained decoding. Strongly preferred over bare JSON
                when the expected shape is known.

        Returns:
            Parsed JSON dict from the LLM response.

        Raises:
            LLMError: If every attempt fails or the response is not valid JSON.
        """
        last_error: Exception | None = None
        for attempt in range(self.JSON_MAX_ATTEMPTS):
            if attempt:
                await asyncio.sleep(min(2.0 ** (attempt - 1), 8.0))
            # Escalate temperature on each retry. At the configured 0.1 a small
            # model tends to reproduce byte-identical output, so a plain retry
            # re-raises the same parse error; nudging the sampling distribution
            # is what gives the re-ask a chance to differ.
            retry_temperature = None if attempt == 0 else min(0.1 * (2**attempt), 0.8)
            response = await self.complete(
                prompt,
                system_prompt,
                temperature=retry_temperature,
                json_schema=json_schema,
            )
            try:
                return json.loads(extract_json_block(response))
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "Malformed JSON from LLM (attempt %d/%d): %s",
                    attempt + 1,
                    self.JSON_MAX_ATTEMPTS,
                    exc,
                )
        logger.error("Failed to parse LLM JSON response: %s", last_error)
        raise LLMError(f"Failed to parse LLM JSON response: {last_error}") from last_error

    async def _call_provider(
        self,
        prompt: str,
        system_prompt: str | None,
        *,
        temperature: float | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        """Call the configured LLM provider.

        This method dispatches to the appropriate provider based on settings.
        Currently supports OpenAI-compatible APIs.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt.
            temperature: Optional sampling-temperature override.

        Returns:
            Raw response text from the provider.
        """
        provider = self._settings.llm_provider

        # An Ollama endpoint reached through an OpenAI-compatible base URL must
        # use the native route, otherwise the `format` hint is dropped and any
        # schema constraint is silently a no-op.
        if self._is_ollama():
            return await self._call_ollama(
                prompt, system_prompt, temperature=temperature, json_schema=json_schema
            )

        # Enforce offline mode strictly when set
        if self._settings.engine_mode == "offline" or provider in ("local", "offline", "qwen"):
            return await self._call_local_model_server(
                prompt, system_prompt, temperature=temperature, json_schema=json_schema
            )
        elif provider in ("openai", "deepseek"):
            try:
                return await self._call_openai_compatible(
                    prompt, system_prompt, temperature=temperature, json_schema=json_schema
                )
            except Exception as exc:
                logger.warning("Cloud LLM provider failed (%s); falling back to local model server.", exc)
                return await self._call_local_model_server(
                    prompt, system_prompt, temperature=temperature, json_schema=json_schema
                )
        else:
            raise LLMError(f"Unsupported LLM provider: {provider}")

    async def _call_local_model_server(
        self,
        prompt: str,
        system_prompt: str | None,
        *,
        temperature: float | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        """Run extraction with the fine-tuned local model.

        This used to call the model server's ``/v1/classify`` endpoint for a coarse
        label and then hand-assemble memories with a capitalised-word regex. That
        path never invoked a language model at all, so the tuned extractor was dead
        code and every memory was a truncated `"Speaker: ..."` stub.

        The primary path now calls the inference server's ``/v1/extract``, which
        serves the fine-tuned model and returns typed claims. The regex assembler is
        kept strictly as a last-resort fallback and logs loudly, because silently
        degrading to stubs is what hid this in the first place.
        """
        conversation = self._conversation_text(prompt)

        try:
            claims = await self._extract_via_inference_server(conversation)
        except Exception as exc:  # noqa: BLE001 - deliberate degrade, logged loudly below
            logger.warning(
                "Fine-tuned extraction unavailable (%s: %s); falling back to the "
                "heuristic assembler. Memories will be low quality until the "
                "inference server is reachable.",
                type(exc).__name__,
                exc,
            )
            return await self._heuristic_extract(prompt)

        if claims:
            return json.dumps({"memories": claims, "facts": [], "entities": []})
        return json.dumps({"memories": [], "facts": [], "entities": []})

    def _conversation_text(self, prompt: str) -> str:
        """Flatten the worker's message payload into the extractor's conversation."""
        try:
            payload = json.loads(prompt)
        except (TypeError, ValueError):
            return prompt
        if not isinstance(payload, dict):
            return prompt
        messages = payload.get("messages")
        if not isinstance(messages, list):
            return prompt
        lines: list[str] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            text = message.get("text") or message.get("content") or ""
            if not str(text).strip():
                continue
            role = str(message.get("role") or message.get("speaker") or "user")
            lines.append(f"{role}: {text}")
        return "\n".join(lines) or prompt

    async def _extract_via_inference_server(self, conversation: str) -> list[dict[str, Any]]:
        """Call the inference server and map gold claims onto ExtractedMemory."""
        import httpx

        base = str(
            getattr(self._settings, "inference_server_url", "")
            or "http://inference-server:8002"
        ).rstrip("/")
        timeout = float(getattr(self._settings, "inference_timeout_seconds", 300.0))
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base}/v1/extract",
                json={"conversation": conversation},
            )
            response.raise_for_status()
            payload = response.json()

        memories: list[dict[str, Any]] = []
        for claim in payload.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            text = str(claim.get("text") or "").strip()
            if not text:
                continue
            subject = str(claim.get("subject") or "the user")
            predicate = str(claim.get("predicate") or "").strip()
            object_value = str(claim.get("object") or "").strip()
            summary = f"{subject} {predicate} {object_value}".strip()
            summary = re.sub(r"\s+", " ", summary)
            memory_type = str(claim.get("memory_type") or "fact")
            try:
                memory_type = MemoryType(memory_type).value
            except ValueError:
                memory_type = MemoryType.FACT.value
            memories.append(
                {
                    "title": (summary[:120] or text[:60]).strip(),
                    "content": text,
                    "memory_type": memory_type,
                    "source_type": "user_explicit",
                    "structured_data": {
                        "subject": subject,
                        "predicate": predicate,
                        "object": object_value,
                        "polarity": claim.get("polarity"),
                        "status": claim.get("status"),
                        "evidence": claim.get("evidence"),
                        "confidence": claim.get("confidence"),
                    },
                    "tags": [],
                    "entities": [value for value in (subject, object_value) if value],
                }
            )
        return memories

    async def _heuristic_extract(self, prompt: str) -> str:
        """Last-resort regex assembler. Not a substitute for the tuned model."""
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

        if getattr(self._settings, "local_model_server_enabled", True):
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

        memories_out: list[dict] = []
        for idx, text in enumerate(texts_to_classify):
            pred_label = normalize_memory_type_label(
                predictions[idx].get("label") if idx < len(predictions) else "fact"
            )
            if pred_label == MemoryType.CUSTOM.value:
                pred_label = infer_memory_type(text)
            speaker = parsed_messages[idx].get("speaker", "Speaker") if idx < len(parsed_messages) else "User"

            clean_text = re.sub(r"\[Date:[^\]]+\]", "", text).strip()
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
                "title": f"{speaker}: {clean_text[:50].strip()}",
                "content": f"{speaker}: {clean_text}",
                "memory_type": pred_label,
                "source_type": "user_explicit",
                "entities": found_entities,
            })

        first_label = normalize_memory_type_label(
            predictions[0].get("label") if predictions else "fact"
        )
        if first_label == MemoryType.CUSTOM.value:
            first_label = infer_memory_type(texts_to_classify[0] if texts_to_classify else prompt)
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

    async def _call_openai_compatible(
        self,
        prompt: str,
        system_prompt: str | None,
        *,
        temperature: float | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        """Call any OpenAI-compatible API (OpenAI, DeepSeek, etc.).

        Uses httpx for async HTTP calls to avoid heavy SDK dependency.
        """
        import httpx

        api_key = self._settings.llm_api_key
        model = self._settings.llm_model
        base_url = self._settings.llm_base_url

        if not api_key:
            logger.info("LLM API key missing (CONTEXTA_LLM_API_KEY). Using local model server fallback.")
            return await self._call_local_model_server(
                prompt, system_prompt, temperature=temperature
            )

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        body: dict = {
            "model": model,
            "messages": messages,
            "temperature": 0.1 if temperature is None else temperature,
        }
        body.update(self._json_mode_body(json_schema))

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if response.status_code >= 400:
                # Surface the provider's own explanation. A bare status code here
                # makes a 400 indistinguishable between a bad request shape, an
                # unknown model, and an exceeded context window.
                raise LLMError(
                    f"LLM provider returned {response.status_code}: "
                    f"{response.text[:500]}"
                )
            data = response.json()
            return data["choices"][0]["message"]["content"]
