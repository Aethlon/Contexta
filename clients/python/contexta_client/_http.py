from __future__ import annotations

import json
import logging
import os
import platform
import random
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urljoin

import httpx

from contexta_client._buffer import DurableBuffer
from contexta_client._types import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    contextaError,
    NotFoundError,
    QuotaExceeded,
    RateLimited,
    ServerError,
    ValidationError,
)

logger = logging.getLogger("contexta.http")

SDK_VERSION = "0.2.0"

try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    pass


def _uuid_v7() -> str:
    timestamp = int(time.time() * 1000)
    rand_bytes = random.getrandbits(74).to_bytes(10, "big")
    uuid_bytes = timestamp.to_bytes(6, "big") + b"\x70" + rand_bytes[:1] + b"\x80" + rand_bytes[1:]
    return str(uuid.UUID(bytes=uuid_bytes, version=7))


def _build_telemetry() -> Dict[str, str]:
    return {
        "sdk_version": SDK_VERSION,
        "python_version": platform.python_version(),
        "os": platform.system().lower(),
        "platform": platform.machine(),
    }


class HTTPClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.contexta.dev/v1",
        timeout: float = 30.0,
        max_retries: int = 3,
        telemetry: bool = True,
        enable_buffer: bool = True,
        buffer_path: Optional[str] = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.telemetry_enabled = telemetry
        self._client = httpx.Client(timeout=httpx.Timeout(timeout))
        self._async_client: Optional[httpx.AsyncClient] = None
        self._buffer = DurableBuffer(buffer_path=buffer_path, enabled=enable_buffer)
        self._telemetry_data = _build_telemetry() if telemetry else {}

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout))
        return self._async_client

    def _headers(self, idempotency_key: Optional[str] = None, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
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

    def _request(
        self,
        method: str,
        endpoint: str,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        is_write: bool = False,
    ) -> Dict[str, Any]:
        if is_write and not idempotency_key:
            idempotency_key = _uuid_v7()

        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        req_headers = self._headers(idempotency_key, extra=headers)

        last_exception: Optional[Exception] = None
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
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        is_write: bool = False,
    ) -> Dict[str, Any]:
        if is_write and not idempotency_key:
            idempotency_key = _uuid_v7()

        client = self._get_async_client()
        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        req_headers = self._headers(idempotency_key, extra=headers)

        last_exception: Optional[Exception] = None
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

    def _parse_error(self, response: httpx.Response) -> Dict[str, Any]:
        try:
            data = response.json()
            if isinstance(data, dict) and "error" in data:
                return data["error"]
            return data
        except (json.JSONDecodeError, ValueError):
            return {"message": response.text}

    def _parse_retry_after(self, response: httpx.Response) -> Optional[int]:
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
            except Exception:
                self._buffer.dead_letter(entry, "async_flush_failure")
        return flushed

    def close(self) -> None:
        self._client.close()
        if self._async_client:
            import asyncio
            try:
                asyncio.get_event_loop().run_until_complete(self._async_client.aclose())
            except RuntimeError:
                pass
