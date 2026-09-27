from __future__ import annotations

import asyncio
import json
import logging
import platform
import random
import ssl
import time
import uuid
from pathlib import Path
from typing import Any, Union
from urllib.parse import urljoin

import httpx

from contexta_client._buffer import DurableBuffer
from contexta_client._types import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    QuotaExceeded,
    RateLimited,
    ServerError,
    ValidationError,
    contextaError,
)

logger = logging.getLogger("contexta.http")

SDK_VERSION = "0.2.0"

try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    pass


def _uuid_v7() -> str:
    timestamp = int(time.time() * 1000) & ((1 << 48) - 1)
    rand_a = random.getrandbits(12)
    rand_b = random.getrandbits(62)
    value = (timestamp << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return str(uuid.UUID(int=value))


def _build_telemetry() -> dict[str, str]:
    return {
        "sdk_version": SDK_VERSION,
        "python_version": platform.python_version(),
        "os": platform.system().lower(),
        "platform": platform.machine(),
    }


TLSConfig = Union[bool, str, bytes, "ssl.SSLContext"]


def _resolve_verify(
    verify_tls: bool,
    ca_bundle: TLSConfig | None,
    ca_bundle_path: str | None,
) -> TLSConfig:
    """Resolve the ``verify`` argument handed to httpx.

    Certificate verification stays on unless the caller explicitly opts out with
    ``verify_tls=False``. A CA bundle (inline or on disk) takes precedence over the
    boolean so the self-signed local gateway can be trusted without weakening
    verification globally.
    """
    if ca_bundle is not None and not verify_tls:
        raise ValueError(
            "Pass either ca_bundle/ca_bundle_path or verify_tls=False, not both: "
            "supplying a CA bundle keeps verification enabled."
        )
    if ca_bundle is not None:
        return ca_bundle
    if ca_bundle_path:
        if not Path(ca_bundle_path).is_file():
            raise ValueError(f"CA bundle not found: {ca_bundle_path}")
        return str(ca_bundle_path)
    return verify_tls


class HTTPClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.contexta.dev/v1",
        timeout: float = 30.0,
        max_retries: int = 3,
        telemetry: bool = True,
        enable_buffer: bool = True,
        buffer_path: str | None = None,
        verify_tls: bool = True,
        ca_bundle: TLSConfig | None = None,
        ca_bundle_path: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.telemetry_enabled = telemetry
        self.verify = _resolve_verify(verify_tls, ca_bundle, ca_bundle_path)
        self._closed = False
        self._client = httpx.Client(timeout=httpx.Timeout(timeout), verify=self.verify)
        self._async_client: httpx.AsyncClient | None = None
        self._buffer = DurableBuffer(buffer_path=buffer_path, enabled=enable_buffer)
        self._telemetry_data = _build_telemetry() if telemetry else {}

    @property
    def organization_url(self) -> str:
        """Base URL with the trailing API version segment removed.

        Health checks live at the service root rather than under the versioned
        prefix, so ``ping`` has to escape ``/v1``.
        """
        base = self.base_url
        if base.endswith("/v1"):
            return base[: -len("/v1")]
        return base

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                verify=self.verify,
            )
        return self._async_client

    def _headers(self, idempotency_key: str | None = None, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": f"contexta-python/{SDK_VERSION}",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if extra:
            headers.update(extra)
        return headers

    def _resolve_url(self, endpoint: str, absolute: bool = False) -> str:
        base = self.organization_url if absolute else self.base_url
        return urljoin(base + "/", endpoint.lstrip("/"))

    def _request(
        self,
        method: str,
        endpoint: str,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        headers: dict[str, str] | None = None,
        is_write: bool = False,
        absolute: bool = False,
    ) -> dict[str, Any]:
        if is_write and not idempotency_key:
            idempotency_key = _uuid_v7()

        url = self._resolve_url(endpoint, absolute)
        req_headers = self._headers(idempotency_key, extra=headers)

        last_exception: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                start = time.monotonic()
                response = self._client.request(
                    method=method,
                    url=url,
                    json=body,
                    params=params,
                    headers=req_headers,
                )
                duration = time.monotonic() - start
                self._record_telemetry(endpoint, response.status_code, duration)

                if response.status_code < 300:
                    if response.status_code == 204:
                        return {}
                    return response.json()

                error_data = self._parse_error(response)
                if response.status_code == 401:
                    raise AuthenticationError(error_data.get("message", "Invalid API key"))
                if response.status_code == 403:
                    raise AuthorizationError(error_data.get("message", "Insufficient permissions"))
                if response.status_code == 404:
                    raise NotFoundError(error_data.get("message", "Resource not found"))
                if response.status_code == 409:
                    raise ConflictError(error_data.get("message", "Conflict"))
                if response.status_code == 422:
                    raise ValidationError(
                        message=error_data.get("message", "Validation error"),
                        fields=error_data.get("fields"),
                    )
                if response.status_code == 429:
                    retry_after = self._parse_retry_after(response)
                    if attempt < self.max_retries:
                        wait = retry_after or (2 ** attempt)
                        logger.warning("Rate limited, retrying in %s seconds", wait)
                        time.sleep(wait)
                        continue
                    error_type = error_data.get("type", "")
                    if error_type == "quota_exceeded":
                        raise QuotaExceeded(error_data.get("message", "Quota exceeded"))
                    raise RateLimited(
                        message=error_data.get("message", "Rate limited"),
                        retry_after=retry_after or 0,
                    )
                if response.status_code >= 500:
                    if attempt < self.max_retries:
                        wait = 2 ** attempt
                        logger.warning("Server error %s, retrying in %s seconds", response.status_code, wait)
                        time.sleep(wait)
                        continue
                    raise ServerError(
                        message=error_data.get("message", "Server error"),
                        status_code=response.status_code,
                    )
                raise contextaError(error_data.get("message", f"HTTP {response.status_code}"))

            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
                last_exception = e
                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    logger.warning("Network error: %s, retrying in %s seconds", e, wait)
                    if is_write and self._buffer.enabled:
                        self._buffer.enqueue(endpoint, body or {}, idempotency_key or "", req_headers)
                    time.sleep(wait)
                    continue
                raise ServerError(message=str(e), status_code=0)

        if last_exception:
            raise ServerError(message=str(last_exception), status_code=0)
        return {}

    async def _async_request(
        self,
        method: str,
        endpoint: str,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        headers: dict[str, str] | None = None,
        is_write: bool = False,
        absolute: bool = False,
    ) -> dict[str, Any]:
        if is_write and not idempotency_key:
            idempotency_key = _uuid_v7()

        client = self._get_async_client()
        url = self._resolve_url(endpoint, absolute)
        req_headers = self._headers(idempotency_key, extra=headers)

        last_exception: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                start = time.monotonic()
                response = await client.request(
                    method=method,
                    url=url,
                    json=body,
                    params=params,
                    headers=req_headers,
                )
                duration = time.monotonic() - start
                self._record_telemetry(endpoint, response.status_code, duration)

                if response.status_code < 300:
                    if response.status_code == 204:
                        return {}
                    return response.json()

                error_data = self._parse_error(response)
                if response.status_code == 401:
                    raise AuthenticationError(error_data.get("message", "Invalid API key"))
                if response.status_code == 403:
                    raise AuthorizationError(error_data.get("message", "Insufficient permissions"))
                if response.status_code == 404:
                    raise NotFoundError(error_data.get("message", "Resource not found"))
                if response.status_code == 409:
                    raise ConflictError(error_data.get("message", "Conflict"))
                if response.status_code == 422:
                    raise ValidationError(
                        message=error_data.get("message", "Validation error"),
                        fields=error_data.get("fields"),
                    )
                if response.status_code == 429:
                    retry_after = self._parse_retry_after(response)
                    if attempt < self.max_retries:
                        wait = retry_after or (2 ** attempt)
                        logger.warning("Rate limited, retrying in %s seconds", wait)
                        await self._async_sleep(wait)
                        continue
                    error_type = error_data.get("type", "")
                    if error_type == "quota_exceeded":
                        raise QuotaExceeded(error_data.get("message", "Quota exceeded"))
                    raise RateLimited(
                        message=error_data.get("message", "Rate limited"),
                        retry_after=retry_after or 0,
                    )
                if response.status_code >= 500:
                    if attempt < self.max_retries:
                        wait = 2 ** attempt
                        logger.warning("Server error %s, retrying in %s seconds", response.status_code, wait)
                        await self._async_sleep(wait)
                        continue
                    raise ServerError(
                        message=error_data.get("message", "Server error"),
                        status_code=response.status_code,
                    )
                raise contextaError(error_data.get("message", f"HTTP {response.status_code}"))

            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
                last_exception = e
                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    logger.warning("Network error: %s, retrying in %s seconds", e, wait)
                    if is_write and self._buffer.enabled:
                        self._buffer.enqueue(endpoint, body or {}, idempotency_key or "", req_headers)
                    await self._async_sleep(wait)
                    continue
                raise ServerError(message=str(e), status_code=0)

        if last_exception:
            raise ServerError(message=str(last_exception), status_code=0)
        return {}

    def _parse_error(self, response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
            if isinstance(data, dict) and "error" in data:
                return data["error"]
            return data
        except (json.JSONDecodeError, ValueError):
            return {"message": response.text}

    def _parse_retry_after(self, response: httpx.Response) -> int | None:
        val = response.headers.get("Retry-After")
        if val:
            try:
                return int(val)
            except ValueError:
                pass
        return None

    def _record_telemetry(self, endpoint: str, status_code: int, duration: float) -> None:
        if not self.telemetry_enabled:
            return
        self._telemetry_data.setdefault("endpoint_counts", {})
        key = f"{endpoint}:{status_code}"
        self._telemetry_data["endpoint_counts"][key] = self._telemetry_data["endpoint_counts"].get(key, 0) + 1

    @staticmethod
    async def _async_sleep(seconds: float) -> None:
        import asyncio
        await asyncio.sleep(seconds)

    def flush_buffer(self) -> int:
        """Drain the durable offline queue, returning the number of entries replayed."""
        return self._buffer.flush(self)

    async def flush_buffer_async(self) -> int:
        entries = self._buffer.dequeue_all()
        if not entries:
            return 0
        flushed = 0
        for entry in entries:
            try:
                await self._async_request(
                    method="POST",
                    endpoint=entry["endpoint"],
                    body=entry["body"],
                    idempotency_key=entry["idempotency_key"],
                    headers=entry.get("headers"),
                )
                flushed += 1
            except Exception:  # noqa: BLE001 - a dead-letter must never abort the drain
                self._buffer.dead_letter(entry, "async_flush_failure")
        return flushed

    def close(self) -> None:
        """Release pooled connections. Safe to call more than once.

        When called from inside a running event loop the async pool is left alone;
        use ``aclose`` (or ``await client.close()`` on ``AsyncContexta``) instead.
        """
        if self._closed:
            return
        self._closed = True
        self._client.close()
        if self._async_client is not None:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                try:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(self._async_client.aclose())
                    loop.close()
                except Exception:
                    logger.debug("Async transport left for garbage collection", exc_info=True)
                self._async_client = None

    async def aclose(self) -> None:
        """Asynchronously release pooled connections. Safe to call more than once."""
        if self._async_client is not None:
            client, self._async_client = self._async_client, None
            await client.aclose()
        if not self._closed:
            self.close()
