"""Authentication and account management routes (public)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.db import get_db_session
from contexta.models.account import Account, Organization, OrganizationMember
from contexta.repositories.account_repo import AccountRepository, OrganizationRepository
from contexta.services.auth import create_jwt, hash_password, verify_password, verify_jwt

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=200)
    organization_name: str = Field(min_length=1, max_length=200)
    organization_slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")


class SigninRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    token: str
    account_id: str
    organization_id: str
    email: str
    display_name: str


class MessageResponse(BaseModel):
    message: str


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    account_repo = AccountRepository(session)
    org_repo = OrganizationRepository(session)

    existing = await account_repo.find_by_email(payload.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    existing_org = await org_repo.find_by_slug(payload.organization_slug)
    if existing_org:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An organization with this slug already exists.",
        )

    password_hash = hash_password(payload.password)
    account = Account(
        email=payload.email,
        password_hash=password_hash,
        display_name=payload.display_name,
        status="active",
    )
    account = await account_repo.create(account)

    org = Organization(
        name=payload.organization_name,
        slug=payload.organization_slug,
        plan_code="free",
        status="active",
    )
    org = await org_repo.create(org)

    member = OrganizationMember(
        organization_id=org.id,
        account_id=account.id,
        role="owner",
    )
    session.add(member)
    await session.flush()

    token = create_jwt(account.id, org.id)

    return AuthResponse(
        token=token,
        account_id=str(account.id),
        organization_id=str(org.id),
        email=account.email,
        display_name=account.display_name,
    )


@router.post("/signin", response_model=AuthResponse)
async def signin(
    payload: SigninRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    account_repo = AccountRepository(session)

    account = await account_repo.find_by_email(payload.email)
    if not account or not account.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not verify_password(payload.password, account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    # Get the first active organization membership
    org_member = account.memberships[0] if account.memberships else None
    if not org_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No organization membership found.",
        )

    account.last_login_at = datetime.now(timezone.utc)
    await session.flush()

    token = create_jwt(account.id, org_member.organization_id)

    return AuthResponse(
        token=token,
        account_id=str(account.id),
        organization_id=str(org_member.organization_id),
        email=account.email,
        display_name=account.display_name,
    )


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    payload: VerifyEmailRequest,
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    try:
        data = verify_jwt(payload.token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    account_repo = AccountRepository(session)
    account_id = uuid.UUID(data["sub"])
    await account_repo.update(account_id, {"email_verified": True})

    return MessageResponse(message="Email verified successfully.")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    account_repo = AccountRepository(session)
    account = await account_repo.find_by_email(payload.email)
    if account:
        token = create_jwt(account.id, uuid.UUID(int=0), expires_delta=timedelta(hours=1))
    return MessageResponse(message="If an account exists, a password reset link has been sent.")
