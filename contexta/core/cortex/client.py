"""Async client for TypeSafe AI's JEV System One API."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from contexta.core.cortex.decisions import CortexTelemetry

logger = logging.getLogger(__name__)


class JevClientError(Exception):
    """Base exception for JEV client failures."""


class JevTimeoutError(JevClientError):
    """Raised when a JEV call times out."""


class JevClient:
    """High-speed asynchronous client for JEV System One decision API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.typesafe.ai/v1/systemone",
        model: str = "jev-latest",
        timeout_seconds: float = 1.5,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds

    @property
    def is_configured(self) -> bool:
        """Return True if an API key is present."""
        return bool(self._api_key and self._api_key.strip())

    async def evaluate(
        self,
        state: str,
        questions: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, CortexTelemetry]:
        """Send a state and structured questions payload to JEV.

        Returns:
            Tuple of (raw_json_response or None, CortexTelemetry)
        """
        if not self.is_configured:
            return None, CortexTelemetry(
                latency_ms=0.0,
                source="heuristic_fallback",
                error="JEV API key not configured",
            )

        headers = {
            "Authorization": f"Bearer {self._api_key.strip()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "model": self._model,
            "state": state,
            "questions": questions,
        }

        t_start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    self._base_url,
                    json=payload,
                    headers=headers,
                )
                latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
                request_id = response.headers.get("x-request-id") or response.headers.get("request-id")

                if response.status_code == 200:
                    data = response.json()
                    req_id = data.get("id") or request_id
                    telemetry = CortexTelemetry(
                        latency_ms=latency_ms,
                        source="jev",
                        jev_request_id=str(req_id) if req_id else None,
                    )
                    return data, telemetry

                # Non-200 response
                err_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.warning("JEV call failed: %s (latency=%sms)", err_msg, latency_ms)
                return None, CortexTelemetry(
                    latency_ms=latency_ms,
                    source="heuristic_fallback",
                    jev_request_id=request_id,
                    error=err_msg,
                )

        except httpx.TimeoutException as exc:
            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            logger.warning("JEV call timed out after %sms (limit=%ss)", latency_ms, self._timeout_seconds)
            return None, CortexTelemetry(
                latency_ms=latency_ms,
                source="heuristic_fallback",
                error=f"Timeout after {latency_ms}ms: {exc}",
            )
        except Exception as exc:
            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            logger.warning("JEV request encountered unexpected error: %s (latency=%sms)", exc, latency_ms)
            return None, CortexTelemetry(
                latency_ms=latency_ms,
                source="heuristic_fallback",
                error=str(exc),
            )
