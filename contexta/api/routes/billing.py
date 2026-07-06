"""Billing and usage routes backed by Dodo Payments."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.db import get_db_session
from contexta.models.account import Organization
from contexta.models.usage import UsageDaily, UsageEvent, UsagePeriod
from contexta.repositories.account_repo import OrganizationRepository
from contexta.services.dodo_billing import DodoBilling, DodoBillingError

router = APIRouter(tags=["billing"])


class CheckoutRequest(BaseModel):
    price_id: str
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    url: str


class PortalResponse(BaseModel):
    url: str


class SubscriptionResponse(BaseModel):
    dodo_subscription_id: str | None
    plan_code: str
    status: str
    period_start: date | None
    period_end: date | None


class UsageSummaryResponse(BaseModel):
    period_start: date
    period_end: date
    plan_code: str
    observations: int
    retrievals: int
    reranks: int
    memory_writes: int
    active_memories: int
    overage_cents: int
    invoice_id: str | None


class UsageEventItem(BaseModel):
    id: str
    classification: str
    units: int
    llm_tokens_in: int
    llm_tokens_out: int
    bytes_in: int
    bytes_out: int
    latency_ms: int
    status_code: int
    endpoint: str
    method: str
    occurred_at: datetime

    class Config:
        from_attributes = True


class UsageEventsResponse(BaseModel):
    items: list[UsageEventItem]
    total: int
    offset: int
    limit: int


class WebhookResponse(BaseModel):
    received: bool


class WebhookEvent(BaseModel):
    event: str
    data: dict[str, Any]


def _get_dodo_billing(request: Request) -> DodoBilling:
    settings = request.app.state.settings
    return DodoBilling(
        api_key=settings.dodo_api_key,
        mode=settings.dodo_mode,
    )


async def _resolve_organization(
    request: Request,
    session: AsyncSession,
) -> Organization:
    org_id = request.state.organization_id
    if not org_id:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    repo = OrganizationRepository(session)
    org = await repo.find_by_id(uuid.UUID(org_id))
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return org


@router.post("/v1/billing/checkout", response_model=CheckoutResponse)
async def create_checkout(
    payload: CheckoutRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> CheckoutResponse:
    org = await _resolve_organization(request, session)
    if not org.dodo_customer_id:
        raise HTTPException(status_code=400, detail="No Dodo customer ID. Complete signup first.")

    dodo = _get_dodo_billing(request)
    try:
        url = await dodo.create_checkout_session(
            customer_id=org.dodo_customer_id,
            price_id=payload.price_id,
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
        )
    except DodoBillingError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return CheckoutResponse(url=url)


@router.post("/v1/billing/portal", response_model=PortalResponse)
async def create_portal(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> PortalResponse:
    org = await _resolve_organization(request, session)
    if not org.dodo_customer_id:
        raise HTTPException(status_code=400, detail="No Dodo customer ID.")

    dodo = _get_dodo_billing(request)
    try:
        url = await dodo.create_customer_portal_session(org.dodo_customer_id)
    except DodoBillingError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return PortalResponse(url=url)


@router.get("/v1/billing/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> SubscriptionResponse:
    org = await _resolve_organization(request, session)

    if org.dodo_subscription_id:
        dodo = _get_dodo_billing(request)
        try:
            sub = await dodo.get_subscription(org.dodo_subscription_id)
            return SubscriptionResponse(
                dodo_subscription_id=org.dodo_subscription_id,
                plan_code=org.plan_code,
                status=sub.get("status", org.status),
                period_start=sub.get("current_period_start"),
                period_end=sub.get("current_period_end"),
            )
        except DodoBillingError:
            pass

    return SubscriptionResponse(
        dodo_subscription_id=org.dodo_subscription_id,
        plan_code=org.plan_code,
        status=org.status,
        period_start=None,
        period_end=None,
    )


@router.get("/v1/usage", response_model=UsageSummaryResponse)
async def get_current_usage(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> UsageSummaryResponse:
    org = await _resolve_organization(request, session)
    today = date.today()

    stmt = select(UsagePeriod).where(
        UsagePeriod.organization_id == org.id,
        UsagePeriod.status == "open",
    ).order_by(UsagePeriod.period_start.desc()).limit(1)
    result = await session.execute(stmt)
    period = result.scalar_one_or_none()

    if not period:
        return UsageSummaryResponse(
            period_start=today.replace(day=1),
            period_end=today,
            plan_code=org.plan_code,
            observations=0,
            retrievals=0,
            reranks=0,
            memory_writes=0,
            active_memories=0,
            overage_cents=0,
            invoice_id=None,
        )

    return UsageSummaryResponse(
        period_start=period.period_start,
        period_end=period.period_end,
        plan_code=period.plan_code,
        observations=period.observations,
        retrievals=period.retrievals,
        reranks=period.reranks,
        memory_writes=period.memory_writes,
        active_memories=period.active_memories,
        overage_cents=period.overage_cents,
        invoice_id=period.invoice_id,
    )


@router.get("/v1/usage/events", response_model=UsageEventsResponse)
async def list_usage_events(
    request: Request,
    offset: int = 0,
    limit: int = 100,
    classification: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> UsageEventsResponse:
    org = await _resolve_organization(request, session)

    query = select(UsageEvent).where(UsageEvent.organization_id == org.id)
    count_query = select(func.count(UsageEvent.id)).where(UsageEvent.organization_id == org.id)

    if classification:
        query = query.where(UsageEvent.classification == classification)
        count_query = count_query.where(UsageEvent.classification == classification)

    query = query.order_by(UsageEvent.occurred_at.desc()).offset(offset).limit(limit)

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    result = await session.execute(query)
    events = result.scalars().all()

    return UsageEventsResponse(
        items=[UsageEventItem.model_validate(e) for e in events],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/v1/webhooks/dodo", response_model=WebhookResponse)
async def dodo_webhook(
    payload: WebhookEvent,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    x_signature: str | None = Header(default=None),
) -> WebhookResponse:
    settings = request.app.state.settings

    if settings.dodo_webhook_secret and x_signature:
        body = await request.body()
        expected = hmac.new(
            settings.dodo_webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        if x_signature != expected:
            raise HTTPException(status_code=401, detail="Invalid webhook signature.")

    event = payload.event
    data = payload.data
    org_repo = OrganizationRepository(session)

    if event == "subscription.created":
        customer_id = data.get("customer_id")
        sub_id = data.get("id")
        price_id = data.get("price_id", "")
        org = await org_repo.find_by_customer_id(customer_id)
        if org:
            await org_repo.update_plan(org.id, price_id, sub_id)

    elif event == "subscription.updated":
        customer_id = data.get("customer_id")
        sub_id = data.get("id")
        price_id = data.get("price_id", "")
        org = await org_repo.find_by_customer_id(customer_id)
        if org:
            await org_repo.update_plan(org.id, price_id, sub_id)

    elif event == "subscription.deleted":
        customer_id = data.get("customer_id")
        org = await org_repo.find_by_customer_id(customer_id)
        if org:
            await org_repo.update(org.id, {
                "plan_code": "free",
                "dodo_subscription_id": None,
                "status": "canceled",
            })

    elif event == "invoice.payment_succeeded":
        customer_id = data.get("customer_id")
        invoice_id = data.get("id")
        period_start = data.get("period_start")
        period_end = data.get("period_end")
        total_cents = data.get("total", 0)
        org = await org_repo.find_by_customer_id(customer_id)
        if org and period_start and period_end:
            stmt = select(UsagePeriod).where(
                UsagePeriod.organization_id == org.id,
                UsagePeriod.period_start == period_start,
            )
            result = await session.execute(stmt)
            period = result.scalar_one_or_none()
            if period:
                period.status = "closed"
                period.closed_at = datetime.utcnow()
                period.invoice_id = invoice_id
                period.overage_cents = total_cents
            else:
                session.add(UsagePeriod(
                    organization_id=org.id,
                    period_start=period_start,
                    period_end=period_end,
                    plan_code=org.plan_code,
                    status="closed",
                    invoice_id=invoice_id,
                    overage_cents=total_cents,
                    closed_at=datetime.utcnow(),
                ))

    elif event == "invoice.payment_failed":
        customer_id = data.get("customer_id")
        org = await org_repo.find_by_customer_id(customer_id)
        if org:
            await org_repo.update(org.id, {"status": "past_due"})

    return WebhookResponse(received=True)
