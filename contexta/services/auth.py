"""Authentication service: password hashing, JWT creation & verification."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from contexta.config.settings import get_settings

settings = get_settings()

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_ctx.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_ctx.verify(password, password_hash)


def create_jwt(
    account_id: uuid.UUID,
    organization_id: uuid.UUID,
    *,
    expires_delta: timedelta | None = None,
) -> str:
    payload = {
        "sub": str(account_id),
        "org": str(organization_id),
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + (expires_delta or timedelta(days=7)),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def verify_jwt(token: str) -> dict[str, str]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired.")
    except jwt.InvalidTokenError as exc:
        raise ValueError(f"Invalid token: {exc}")
