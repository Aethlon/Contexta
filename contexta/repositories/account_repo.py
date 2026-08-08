"""Account and Organization repositories."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.models.account import Account, Organization


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, account: Account) -> Account:
        self._session.add(account)
        await self._session.flush()
        return account

    async def find_by_email(self, email: str) -> Account | None:
        stmt = select(Account).where(Account.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_id(self, account_id: uuid.UUID) -> Account | None:
        stmt = select(Account).where(Account.id == account_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, account_id: uuid.UUID, values: dict[str, Any]) -> bool:
        stmt = update(Account).where(Account.id == account_id).values(**values)
        result = await self._session.execute(stmt)
        return result.rowcount > 0


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, org: Organization) -> Organization:
        self._session.add(org)
        await self._session.flush()
        return org

    async def find_by_id(self, org_id: uuid.UUID) -> Organization | None:
        stmt = select(Organization).where(Organization.id == org_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_customer_id(self, dodo_customer_id: str) -> Organization | None:
        stmt = select(Organization).where(
            Organization.dodo_customer_id == dodo_customer_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_slug(self, slug: str) -> Organization | None:
        stmt = select(Organization).where(Organization.slug == slug)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_plan(
        self, org_id: uuid.UUID, plan_code: str, dodo_subscription_id: str | None = None
    ) -> bool:
        values: dict[str, Any] = {"plan_code": plan_code}
        if dodo_subscription_id is not None:
            values["dodo_subscription_id"] = dodo_subscription_id
        stmt = update(Organization).where(Organization.id == org_id).values(**values)
        result = await self._session.execute(stmt)
        return result.rowcount > 0

    async def update(self, org_id: uuid.UUID, values: dict[str, Any]) -> bool:
        stmt = update(Organization).where(Organization.id == org_id).values(**values)
        result = await self._session.execute(stmt)
        return result.rowcount > 0
