"""Authentication and account management routes (public)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.db import get_db_session
from contexta.models.account import Account, Organization, OrganizationMember
from contexta.repositories.account_repo import AccountRepository, OrganizationRepository
from contexta.services.auth import create_jwt, hash_password, verify_jwt, verify_password


def _derive_name(email: str) -> str:
    return email.split("@")[0].replace(".", " ").replace("_", " ").title()


def _derive_slug(email: str) -> str:
    return email.split("@")[0].replace(".", "-").replace("_", "-").lower()

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    organization_name: str | None = Field(default=None, min_length=1, max_length=200)
    organization_slug: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")


class SigninRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    token: str
    account_id: str
    organization_id: str
    email: str
    display_name: str
    must_reset_password: bool = False
    onboarding_completed: bool = False


class MessageResponse(BaseModel):
    message: str


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class EmergencyWipeResetRequest(BaseModel):
    email: EmailStr
    confirmation: str
    new_password: str = Field(min_length=8, max_length=128)


class OnboardingMemoryItem(BaseModel):
    title: str
    content: str
    memory_type: str = "fact"
    tags: list[str] = Field(default_factory=list)
    structured_data: dict | None = None
    confidence: float = 1.0
    importance: float = 0.85


class OnboardingRequest(BaseModel):
    user_id: str
    organization_id: str
    name: str = Field(min_length=1, max_length=100)
    age: str | None = None
    favorite_color: str | None = None
    hobbies: str | None = None
    bio: str | None = None
    companion_role: str | None = None
    preferences: str | None = None
    memories: list[OnboardingMemoryItem] | None = None


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

    display_name = payload.display_name or _derive_name(payload.email)
    org_name = payload.organization_name or display_name
    org_slug = payload.organization_slug or _derive_slug(payload.email)

    existing_org = await org_repo.find_by_slug(org_slug)
    if existing_org:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An organization with this slug already exists.",
        )

    password_hash = hash_password(payload.password)
    account = Account(
        email=payload.email,
        password_hash=password_hash,
        display_name=display_name,
        status="active",
    )
    account = await account_repo.create(account)

    org = Organization(
        name=org_name,
        slug=org_slug,
        plan_code="sovereign",
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
        must_reset_password=False,
        onboarding_completed=False,
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

    account.last_login_at = datetime.utcnow()
    await session.flush()

    token = create_jwt(account.id, org_member.organization_id)

    # Check if user is on default credentials
    is_default_password = verify_password("password1234", account.password_hash) or verify_password("password123", account.password_hash)

    # Check if user has completed onboarding by looking for a profile memory
    from contexta.repositories.memory_repo import MemoryRepository
    memory_repo = MemoryRepository(session, org_member.organization_id)
    user_memories = await memory_repo.get_by_user(account.id, limit=50)
    has_profile_memory = any(
        m.memory_type in ("profile", "identity", "fact")
        or any(t in ("onboarding", "profile", "identity") for t in (m.tags or []))
        for m in user_memories
    )

    return AuthResponse(
        token=token,
        account_id=str(account.id),
        organization_id=str(org_member.organization_id),
        email=account.email,
        display_name=account.display_name,
        must_reset_password=is_default_password,
        onboarding_completed=has_profile_memory,
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    account_repo = AccountRepository(session)
    account = await account_repo.find_by_email(payload.email)
    if not account or not account.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or current password.",
        )

    if not verify_password(payload.current_password, account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password does not match.",
        )

    account.password_hash = hash_password(payload.new_password)
    account.updated_at = datetime.utcnow()
    await session.commit()

    return MessageResponse(message="Master password updated successfully. Please authenticate again.")


@router.post("/emergency-wipe-reset", response_model=MessageResponse)
async def emergency_wipe_reset(
    payload: EmergencyWipeResetRequest,
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    if payload.confirmation.strip().upper() != "WIPE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must type 'WIPE' to confirm irreversible vault shredding.",
        )

    account_repo = AccountRepository(session)
    account = await account_repo.find_by_email(payload.email)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found for this email.",
        )

    org_member = account.memberships[0] if account.memberships else None
    if org_member:
        from contexta.repositories.memory_repo import MemoryRepository
        memory_repo = MemoryRepository(session, org_member.organization_id)
        # Irreversibly shred and purge all memories, vectors, and entity nodes
        await memory_repo.purge_all_for_org()

    # Reset credentials and profile
    account.password_hash = hash_password(payload.new_password)
    account.display_name = "User"
    account.updated_at = datetime.utcnow()
    await session.commit()

    return MessageResponse(
        message="Vault data cryptographically shredded and purged. Master password has been reset."
    )


@router.post("/onboarding", response_model=MessageResponse)
async def complete_onboarding(
    payload: OnboardingRequest,
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    org_id = uuid.UUID(payload.organization_id)
    user_id = uuid.UUID(payload.user_id)

    from contexta.core.schemas import ExtractedMemory
    from contexta.core.types import MemoryType, SourceType
    from contexta.repositories.memory_repo import MemoryRepository

    memory_repo = MemoryRepository(session, org_id)

    # 1. Store custom conversational memories if provided by the interactive onboarding agent
    if payload.memories:
        for item in payload.memories:
            try:
                mem_type = MemoryType(item.memory_type.lower())
            except ValueError:
                mem_type = MemoryType.FACT

            mem = ExtractedMemory(
                title=item.title,
                content=item.content,
                memory_type=mem_type,
                source_type=SourceType.USER_EXPLICIT,
                confidence=item.confidence,
                importance=item.importance,
                tags=list(set(["onboarding", "personal_context"] + item.tags)),
                structured_data=item.structured_data,
            )
            await memory_repo.persist(
                user_id=user_id,
                organization_id=org_id,
                session_id=None,
                memory=mem,
                confidence=item.confidence,
                importance=item.importance,
                is_pinned=True,
            )

    # 2. Identity & Profile Memory
    profile_facts = [f"User's name is {payload.name}."]
    if payload.age:
        profile_facts.append(f"User is {payload.age} years old.")
    if payload.favorite_color:
        profile_facts.append(f"User's favorite color / aesthetic is {payload.favorite_color}.")
    if payload.hobbies:
        profile_facts.append(f"User's hobbies include: {payload.hobbies}.")
    if payload.bio:
        profile_facts.append(f"User bio: {payload.bio}.")

    identity_memory = ExtractedMemory(
        title="Personal Profile & Identity",
        content=" ".join(profile_facts),
        memory_type=MemoryType.FACT,
        source_type=SourceType.USER_EXPLICIT,
        confidence=1.0,
        importance=0.95,
        tags=["onboarding", "profile", "identity", "soul"],
        structured_data={
            "name": payload.name,
            "age": payload.age,
            "favorite_color": payload.favorite_color,
            "hobbies": payload.hobbies,
            "bio": payload.bio,
        },
    )
    await memory_repo.persist(
        user_id=user_id,
        organization_id=org_id,
        session_id=None,
        memory=identity_memory,
        confidence=1.0,
        importance=0.95,
        is_pinned=True,
    )

    # 3. Preferences & Assistant Role Memory (if provided)
    if payload.companion_role or payload.preferences:
        pref_facts = []
        if payload.companion_role:
            pref_facts.append(f"Primary AI companion role: {payload.companion_role}.")
        if payload.preferences:
            pref_facts.append(f"User personal preferences: {payload.preferences}.")

        pref_memory = ExtractedMemory(
            title="Personal Assistant Preferences",
            content=" ".join(pref_facts),
            memory_type=MemoryType.PREFERENCE,
            source_type=SourceType.USER_EXPLICIT,
            confidence=1.0,
            importance=0.9,
            tags=["onboarding", "preferences", "assistant"],
            structured_data={
                "companion_role": payload.companion_role,
                "preferences": payload.preferences,
            },
        )
        await memory_repo.persist(
            user_id=user_id,
            organization_id=org_id,
            session_id=None,
            memory=pref_memory,
            confidence=1.0,
            importance=0.9,
            is_pinned=True,
        )

    # Update account display name
    account_repo = AccountRepository(session)
    await account_repo.update(user_id, {"display_name": payload.name})
    await session.commit()

    return MessageResponse(message="Onboarding memories stored successfully.")


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
    return MessageResponse(message="If an account exists, emergency wipe and reset is available via the dashboard.")

