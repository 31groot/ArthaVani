"""Authentication helpers: Argon2 password hashing and JWT bearer tokens."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from config.settings import settings
from finance_agent.persistence import get_user_by_id

# Tuned to OWASP Argon2id parameters (19 MiB memory, 2 iterations, 1 thread)
# so password hashing/verification runs in ~100ms on Render's shared vCPU
# instead of stalling for 1+ seconds, while still verifying existing hashes.
password_hash = PasswordHash(
    (
        Argon2Hasher(
            time_cost=2,
            memory_cost=19456,
            parallelism=1,
        ),
    )
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

# Short-lived in-memory cache so burst requests after login (/auth/me,
# /integrations/groww, /dashboard, /voice) do not hit Postgres 4 times
# for the exact same user row within a few hundred milliseconds.
_USER_CACHE_TTL_SECONDS = 30.0
_user_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _get_cached_user(user_id: str) -> dict[str, Any] | None:
    entry = _user_cache.get(user_id)
    if entry is None:
        return None
    cached_at, user = entry
    if (time.monotonic() - cached_at) >= _USER_CACHE_TTL_SECONDS:
        _user_cache.pop(user_id, None)
        return None
    return user


def _set_cached_user(user_id: str, user: dict[str, Any]) -> None:
    _user_cache[user_id] = (time.monotonic(), user)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(user_id: str) -> str:
    if not settings.API_JWT_SECRET_KEY:
        raise RuntimeError("API_JWT_SECRET_KEY is not configured.")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.API_JWT_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "exp": expires_at,
        "iat": now,
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


def get_user_from_access_token(token: str) -> dict[str, Any]:
    """Resolve a bearer token for non-HTTP transports such as WebSocket.

    This performs a blocking database lookup on cache miss; callers running
    inside an asyncio event loop (the WebSocket handler, `get_current_user`)
    should use `aget_user_from_access_token` instead so the lookup doesn't
    block the loop.
    """
    user_id = _decode_user_id(token)
    cached_user = _get_cached_user(user_id)
    if cached_user is not None:
        return cached_user

    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    _set_cached_user(user_id, user)
    return user


async def aget_user_from_access_token(token: str) -> dict[str, Any]:
    """Async, non-blocking variant of `get_user_from_access_token`."""
    user_id = _decode_user_id(token)
    cached_user = _get_cached_user(user_id)
    if cached_user is not None:
        return cached_user

    user = await asyncio.to_thread(get_user_by_id, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    _set_cached_user(user_id, user)
    return user


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
    return await aget_user_from_access_token(token)