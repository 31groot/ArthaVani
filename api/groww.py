"""User-scoped Groww connection management."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from finance_agent.groww_credentials import (
    decrypt_credentials,
    encrypt_credentials,
)
from finance_agent.persistence import (
    delete_groww_connection,
    get_groww_connection,
    save_groww_connection,
)


def get_status(user_id: str) -> dict[str, Any]:
    connection = get_groww_connection(user_id)
    if connection is None:
        return {"connected": False}

    return {
        "connected": True,
        "auth_mode": connection["auth_mode"],
        "connected_at": connection["created_at"],
        "updated_at": connection["updated_at"],
    }


def connect_once(
    user_id: str,
    auth_mode: str,
    credentials: dict[str, str],
) -> dict[str, Any]:
    if get_groww_connection(user_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Groww is already connected for this user. "
                "Use the replace/update connection flow instead."
            ),
        )

    return replace_connection(user_id, auth_mode, credentials)


def replace_connection(
    user_id: str,
    auth_mode: str,
    credentials: dict[str, str],
) -> dict[str, Any]:
    """Atomically replace the encrypted Groww credentials after validation."""
    encrypted = encrypt_credentials(credentials)
    save_groww_connection(user_id, auth_mode, encrypted)
    return get_status(user_id)


def load_credentials(user_id: str) -> dict[str, Any] | None:
    connection = get_groww_connection(user_id)
    if connection is None:
        return None

    return {
        "auth_mode": connection["auth_mode"],
        "credentials": decrypt_credentials(connection["encrypted_credentials"]),
        "updated_at": connection["updated_at"],
    }


def disconnect(user_id: str) -> bool:
    return delete_groww_connection(user_id)
