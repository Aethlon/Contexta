"""Dodo Payments billing integration service."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Any

import httpx


class DodoBillingError(Exception):
    pass


class DodoBilling:
    """Async client for Dodo Payments REST API.

    Handles customer management, subscriptions, checkout sessions,
    customer portal sessions, usage events, and meter creation.
    """

    BASE_URLS = {
        "test": "https://test.dodopayments.com",
        "live": "https://live.dodopayments.com",
    }

    def __init__(self, api_key: str, mode: str = "test") -> None:
        if mode not in self.BASE_URLS:
            raise ValueError(f"Invalid mode '{mode}'. Must be 'test' or 'live'.")
        self.api_key = api_key
        self.base_url = self.BASE_URLS[mode]
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        resp = await self._client.request(method, path, **kwargs)
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}
        if not resp.is_success:
            raise DodoBillingError(
                f"Dodo API error {resp.status_code}: {data.get('detail') or data.get('message') or resp.text}"
            )
        return data

    async def create_customer(self, email: str, name: str) -> str:
        """Create a Dodo Payments customer and return the customer ID."""
        data = await self._request(
            "POST",
            "/customers",
            json={"email": email, "name": name},
        )
        return data["customer_id"]

    async def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """Create a checkout session and return the hosted checkout URL."""
        data = await self._request(
            "POST",
            "/checkout-sessions",
            json={
                "customer_id": customer_id,
                "price_id": price_id,
                "success_url": success_url,
                "cancel_url": cancel_url,
            },
        )
        return data["url"]

    async def create_customer_portal_session(self, customer_id: str) -> str:
        """Create a customer portal session and return the portal URL."""
        data = await self._request(
            "POST",
            "/customer-portal",
            json={"customer_id": customer_id},
        )
        return data["url"]

    async def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        """Retrieve subscription details."""
        return await self._request("GET", f"/subscriptions/{subscription_id}")

    async def change_plan(self, subscription_id: str, new_price_id: str) -> dict[str, Any]:
        """Change the plan (price) on an existing subscription."""
        return await self._request(
            "POST",
            f"/subscriptions/{subscription_id}/change-plan",
            json={"price_id": new_price_id},
        )

    async def cancel_subscription(self, subscription_id: str) -> dict[str, Any]:
        """Cancel an active subscription."""
        return await self._request(
            "POST",
            f"/subscriptions/{subscription_id}/cancel",
        )

    async def ingest_usage_event(
        self,
        customer_id: str,
        event_name: str,
        event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ingest a usage event for metered billing."""
        payload: dict[str, Any] = {
            "customer_id": customer_id,
            "event_name": event_name,
            "properties": metadata or {},
        }
        if event_id:
            payload["idempotency_key"] = event_id
        return await self._request(
            "POST",
            "/usage-events",
            json=payload,
        )

    async def create_meter(
        self,
        name: str,
        event_name: str,
        aggregation_type: str,
    ) -> str:
        """Create a usage meter and return the meter ID."""
        data = await self._request(
            "POST",
            "/meters",
            json={
                "name": name,
                "event_name": event_name,
                "aggregation_type": aggregation_type,
            },
        )
        return data["meter_id"]

    @staticmethod
    def verify_webhook_signature(
        payload: bytes,
        signature: str,
        secret: str,
    ) -> bool:
        """Verify a Dodo Payments webhook HMAC-SHA256 signature."""
        expected = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)
