from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.core.errors import AuthorizationError
from contexta.models.account import Account, OrganizationMember, Project
from contexta.models.identity import Agent, MemoryUser, SessionScope
from contexta.models.session import Session
from contexta.repositories.base import TenantScopedRepository


class AccountRepository:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def _scope(self, statement: Any) -> Any:
        return statement.join(
            OrganizationMember,
            OrganizationMember.account_id == Account.id,
        ).where(OrganizationMember.organization_id == self._tenant_id)

    async def get_by_id(self, account_id: uuid.UUID) -> Account | None:
        result = await self._session.execute(
            self._scope(select(Account).where(Account.id == account_id))
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Account | None:
        result = await self._session.execute(
            self._scope(select(Account).where(Account.email == email))
        )
        return result.scalar_one_or_none()

    async def get_all(
        self, *, limit: int = 100, offset: int = 0
    ) -> Sequence[Account]:
        statement = self._scope(select(Account)).order_by(Account.created_at)
        result = await self._session.execute(statement.offset(offset).limit(limit))
        return result.scalars().all()

    async def create(
        self,
        account: Account,
        *,
        organization_id: uuid.UUID | None = None,
        role: str = "member",
    ) -> Account:
        tenant_id = organization_id or self._tenant_id
        if tenant_id != self._tenant_id:
            raise AuthorizationError("The account scope does not match the tenant.")
        self._session.add(account)
        await self._session.flush()
        membership_statement = select(OrganizationMember).where(
            OrganizationMember.organization_id == tenant_id,
            OrganizationMember.account_id == account.id,
        )
        membership = await self._session.execute(membership_statement)
        if membership.scalar_one_or_none() is None:
            self._session.add(
                OrganizationMember(
                    organization_id=tenant_id,
                    account_id=account.id,
                    role=role,
                )
            )
            await self._session.flush()
        return account

    async def update(
        self, account_id: uuid.UUID, values: dict[str, Any]
    ) -> int:
        member_accounts = select(OrganizationMember.account_id).where(
            OrganizationMember.organization_id == self._tenant_id,
            OrganizationMember.account_id == account_id,
        )
        statement = update(Account).where(
            Account.id == account_id,
            Account.id.in_(member_accounts),
        ).values(**values)
        result = await self._session.execute(statement)
        return result.rowcount or 0

    @property
    def tenant_id(self) -> uuid.UUID:
        return self._tenant_id


class MemoryUserRepository(TenantScopedRepository[MemoryUser]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=MemoryUser)

    async def _account_in_tenant(self, account_id: uuid.UUID) -> bool:
        statement = select(Account.id).join(
            OrganizationMember,
            OrganizationMember.account_id == Account.id,
        ).where(
            Account.id == account_id,
            OrganizationMember.organization_id == self.tenant_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def create(self, record: MemoryUser) -> MemoryUser:
        if not await self._account_in_tenant(record.account_id):
            raise AuthorizationError("The account does not belong to the tenant.")
        return await super().create(record)

    async def update_by_id(
        self, record_id: uuid.UUID, values: dict[str, Any]
    ) -> int:
        if values.get("organization_id", self.tenant_id) != self.tenant_id:
            raise AuthorizationError("The memory user scope does not match the tenant.")
        account_id = values.get("account_id")
        if account_id is not None and not await self._account_in_tenant(account_id):
            raise AuthorizationError("The account does not belong to the tenant.")
        return await super().update_by_id(record_id, values)

    async def get_by_account(self, account_id: uuid.UUID) -> MemoryUser | None:
        statement = select(MemoryUser).where(MemoryUser.account_id == account_id)
        result = await self._session.execute(self._scope_select(statement))
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> MemoryUser | None:
        statement = select(MemoryUser).where(MemoryUser.external_id == external_id)
        result = await self._session.execute(self._scope_select(statement))
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        *,
        account_id: uuid.UUID,
        external_id: str | None = None,
        display_name: str | None = None,
        attributes: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[MemoryUser, bool]:
        if not await self._account_in_tenant(account_id):
            raise AuthorizationError("The account does not belong to the tenant.")
        if external_id is not None:
            existing = await self.get_by_external_id(external_id)
        else:
            existing = await self.get_by_account(account_id)
        if existing is not None:
            if existing.account_id != account_id:
                raise AuthorizationError("The external identity belongs to another account.")
            return existing, False
        record = MemoryUser(
            organization_id=self.tenant_id,
            account_id=account_id,
            external_id=external_id,
            display_name=display_name,
            attributes=dict(attributes) if attributes is not None else None,
            metadata_=dict(metadata) if metadata is not None else None,
        )
        return await self.create(record), True


class AgentRepository(TenantScopedRepository[Agent]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=Agent)

    async def _parent_in_tenant(self, model: type[Any], record_id: uuid.UUID) -> bool:
        statement = select(model.id).where(
            model.id == record_id,
            model.organization_id == self.tenant_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def _account_in_tenant(self, account_id: uuid.UUID) -> bool:
        statement = select(Account.id).join(
            OrganizationMember,
            OrganizationMember.account_id == Account.id,
        ).where(
            Account.id == account_id,
            OrganizationMember.organization_id == self.tenant_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def create(self, record: Agent) -> Agent:
        if record.project_id is not None and not await self._parent_in_tenant(
            Project, record.project_id
        ):
            raise AuthorizationError("The project does not belong to the tenant.")
        if record.account_id is not None and not await self._account_in_tenant(
            record.account_id
        ):
            raise AuthorizationError("The account does not belong to the tenant.")
        return await super().create(record)

    async def update_by_id(
        self, record_id: uuid.UUID, values: dict[str, Any]
    ) -> int:
        if values.get("organization_id", self.tenant_id) != self.tenant_id:
            raise AuthorizationError("The agent scope does not match the tenant.")
        project_id = values.get("project_id")
        if project_id is not None and not await self._parent_in_tenant(Project, project_id):
            raise AuthorizationError("The project does not belong to the tenant.")
        account_id = values.get("account_id")
        if account_id is not None and not await self._account_in_tenant(account_id):
            raise AuthorizationError("The account does not belong to the tenant.")
        return await super().update_by_id(record_id, values)

    async def get_by_slug(self, slug: str) -> Agent | None:
        statement = select(Agent).where(Agent.slug == slug)
        result = await self._session.execute(self._scope_select(statement))
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> Agent | None:
        statement = select(Agent).where(Agent.external_id == external_id)
        result = await self._session.execute(self._scope_select(statement))
        return result.scalar_one_or_none()

    async def get_for_project(
        self, project_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> Sequence[Agent]:
        statement = select(Agent).where(Agent.project_id == project_id).order_by(
            Agent.created_at
        )
        result = await self._session.execute(
            self._scope_select(statement).offset(offset).limit(limit)
        )
        return result.scalars().all()

    async def list_active(
        self, *, limit: int = 100, offset: int = 0
    ) -> Sequence[Agent]:
        statement = select(Agent).where(Agent.status == "active").order_by(
            Agent.created_at
        )
        result = await self._session.execute(
            self._scope_select(statement).offset(offset).limit(limit)
        )
        return result.scalars().all()


class ProjectRepository(TenantScopedRepository[Project]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=Project)

    async def update_by_id(
        self, record_id: uuid.UUID, values: dict[str, Any]
    ) -> int:
        if values.get("organization_id", self.tenant_id) != self.tenant_id:
            raise AuthorizationError("The project scope does not match the tenant.")
        return await super().update_by_id(record_id, values)

    async def get_by_slug(self, slug: str) -> Project | None:
        statement = select(Project).where(Project.slug == slug)
        result = await self._session.execute(self._scope_select(statement))
        return result.scalar_one_or_none()

    async def get_for_account(self, account_id: uuid.UUID) -> Sequence[Project]:
        statement = (
            select(Project)
            .join(
                OrganizationMember,
                and_(
                    OrganizationMember.organization_id == Project.organization_id,
                    OrganizationMember.account_id == account_id,
                ),
            )
            .where(Project.organization_id == self.tenant_id)
            .order_by(Project.created_at)
        )
        result = await self._session.execute(statement)
        return result.scalars().all()


class SessionRepository(TenantScopedRepository[Session]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=Session)

    async def update_by_id(
        self, record_id: uuid.UUID, values: dict[str, Any]
    ) -> int:
        if values.get("organization_id", self.tenant_id) != self.tenant_id:
            raise AuthorizationError("The session scope does not match the tenant.")
        return await super().update_by_id(record_id, values)

    async def get_by_user(
        self, user_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> Sequence[Session]:
        statement = select(Session).where(Session.user_id == user_id).order_by(
            Session.started_at.desc()
        )
        result = await self._session.execute(
            self._scope_select(statement).offset(offset).limit(limit)
        )
        return result.scalars().all()

    async def get_active(self, user_id: uuid.UUID | None = None) -> Sequence[Session]:
        statement = select(Session).where(Session.ended_at.is_(None))
        if user_id is not None:
            statement = statement.where(Session.user_id == user_id)
        result = await self._session.execute(
            self._scope_select(statement).order_by(Session.started_at.desc())
        )
        return result.scalars().all()

    async def get_for_agent(self, agent_id: uuid.UUID) -> Sequence[Session]:
        statement = (
            select(Session)
            .join(SessionScope, SessionScope.session_id == Session.id)
            .where(
                SessionScope.organization_id == self.tenant_id,
                SessionScope.agent_id == agent_id,
            )
        )
        result = await self._session.execute(
            self._scope_select(statement).order_by(Session.started_at.desc())
        )
        return result.scalars().all()

    async def get_for_project(self, project_id: uuid.UUID) -> Sequence[Session]:
        statement = (
            select(Session)
            .join(SessionScope, SessionScope.session_id == Session.id)
            .where(
                SessionScope.organization_id == self.tenant_id,
                SessionScope.project_id == project_id,
            )
        )
        result = await self._session.execute(
            self._scope_select(statement).order_by(Session.started_at.desc())
        )
        return result.scalars().all()

    async def get_scope(self, session_id: uuid.UUID) -> SessionScope | None:
        return await SessionScopeRepository(
            self._session, self.tenant_id
        ).get_for_session(session_id)


class SessionScopeRepository(TenantScopedRepository[SessionScope]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=SessionScope)

    async def _parent_in_tenant(self, model: type[Any], record_id: uuid.UUID) -> bool:
        statement = select(model.id).where(
            model.id == record_id,
            model.organization_id == self.tenant_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def _session_in_tenant(self, session_id: uuid.UUID) -> bool:
        statement = select(Session.id).where(
            Session.id == session_id,
            Session.organization_id == self.tenant_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def _account_in_tenant(self, account_id: uuid.UUID) -> bool:
        statement = select(OrganizationMember.account_id).where(
            OrganizationMember.organization_id == self.tenant_id,
            OrganizationMember.account_id == account_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def _validate_scope(self, record: SessionScope) -> None:
        if not await self._session_in_tenant(record.session_id):
            raise AuthorizationError("The session does not belong to the tenant.")
        for model, record_id in (
            (MemoryUser, record.memory_user_id),
            (Agent, record.agent_id),
            (Project, record.project_id),
        ):
            if record_id is not None and not await self._parent_in_tenant(model, record_id):
                raise AuthorizationError("A session scope parent is outside the tenant.")
        if record.account_id is not None and not await self._account_in_tenant(
            record.account_id
        ):
            raise AuthorizationError("The account does not belong to the tenant.")

    async def create(self, record: SessionScope) -> SessionScope:
        await self._validate_scope(record)
        return await super().create(record)

    async def update_by_id(
        self, record_id: uuid.UUID, values: dict[str, Any]
    ) -> int:
        if values.get("organization_id", self.tenant_id) != self.tenant_id:
            raise AuthorizationError("The session scope does not match the tenant.")
        session_id = values.get("session_id")
        if session_id is not None and not await self._session_in_tenant(session_id):
            raise AuthorizationError("The session does not belong to the tenant.")
        for model, field in (
            (MemoryUser, "memory_user_id"),
            (Agent, "agent_id"),
            (Project, "project_id"),
        ):
            parent_id = values.get(field)
            if parent_id is not None and not await self._parent_in_tenant(model, parent_id):
                raise AuthorizationError("A session scope parent is outside the tenant.")
        account_id = values.get("account_id")
        if account_id is not None and not await self._account_in_tenant(account_id):
            raise AuthorizationError("The account does not belong to the tenant.")
        return await super().update_by_id(record_id, values)

    async def get_for_session(self, session_id: uuid.UUID) -> SessionScope | None:
        statement = select(SessionScope).where(SessionScope.session_id == session_id)
        result = await self._session.execute(self._scope_select(statement))
        return result.scalar_one_or_none()

    async def set_scope(
        self,
        session_id: uuid.UUID,
        *,
        account_id: uuid.UUID | None = None,
        memory_user_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SessionScope:
        record = await self.get_for_session(session_id)
        if record is None:
            record = SessionScope(
                organization_id=self.tenant_id,
                session_id=session_id,
                account_id=account_id,
                memory_user_id=memory_user_id,
                user_id=user_id,
                agent_id=agent_id,
                project_id=project_id,
                metadata_=dict(metadata) if metadata is not None else None,
            )
            return await self.create(record)
        if account_id is not None:
            record.account_id = account_id
        if memory_user_id is not None:
            record.memory_user_id = memory_user_id
        if user_id is not None:
            record.user_id = user_id
        if agent_id is not None:
            record.agent_id = agent_id
        if project_id is not None:
            record.project_id = project_id
        if metadata is not None:
            record.metadata_ = dict(metadata)
        await self._validate_scope(record)
        await self._session.flush()
        return record


TenantAccountRepository = AccountRepository
ProjectScopeRepository = ProjectRepository

__all__ = [
    "AccountRepository",
    "AgentRepository",
    "MemoryUserRepository",
    "ProjectRepository",
    "ProjectScopeRepository",
    "SessionRepository",
    "SessionScopeRepository",
    "TenantAccountRepository",
]
