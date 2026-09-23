"""Authentication helpers: Argon2 password hashing and JWT bearer tokens."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from config.settings import settings
from finance_agent.persistence import get_user_by_id

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(user_id: str) -> str:
    if not settings.API_JWT_SECRET_KEY:
        raise RuntimeError("API_JWT_SECRET_KEY is not configured.")

    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.API_JWT_EXPIRE_MINUTES
    )
    payload = {
        "sub": user_id,
        "exp": expires_at,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(
        payload,
        settings.API_JWT_SECRET_KEY,
        algorithm=settings.API_JWT_ALGORITHM,
    )


def _decode_user_id(token: str) -> str:
    if not settings.API_JWT_SECRET_KEY:
        raise RuntimeError("API_JWT_SECRET_KEY is not configured.")

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.API_JWT_SECRET_KEY,
            algorithms=[settings.API_JWT_ALGORITHM],
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has no valid subject.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
    user_id = _decode_user_id(token)
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
