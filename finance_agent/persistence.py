"""Small PostgreSQL persistence layer for API users and Groww connections."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

import psycopg

from config.settings import settings


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS arthavani_users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS groww_connections (
    user_id TEXT PRIMARY KEY REFERENCES arthavani_users(id) ON DELETE CASCADE,
    auth_mode TEXT NOT NULL CHECK (auth_mode IN ('api_key_secret', 'totp')),
    encrypted_credentials TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arthavani_users_email
    ON arthavani_users(email);
"""


def _require_database_url() -> str:
    if not settings.DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is required for API authentication and Groww connections."
        )
    return settings.DATABASE_URL


@contextmanager
def db_connection() -> Iterator[psycopg.Connection]:
    with psycopg.connect(_require_database_url()) as conn:
        yield conn


def initialize_database() -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()


def create_user(user_id: str, email: str, password_hash: str) -> dict[str, Any]:
    with db_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO arthavani_users (id, email, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id, email, password_hash, created_at
                    """,
                    (user_id, email, password_hash),
                )
                row = cur.fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return {
        "id": row[0],
        "email": row[1],
        "password_hash": row[2],
        "created_at": row[3],
    }


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, password_hash, created_at
                FROM arthavani_users
                WHERE email = %s
                """,
                (email,),
            )
            row = cur.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "email": row[1],
        "password_hash": row[2],
        "created_at": row[3],
    }


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, password_hash, created_at
                FROM arthavani_users
                WHERE id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "email": row[1],
        "password_hash": row[2],
        "created_at": row[3],
    }


def save_groww_connection(
    user_id: str,
    auth_mode: str,
    encrypted_credentials: str,
) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO groww_connections
                    (user_id, auth_mode, encrypted_credentials)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    auth_mode = EXCLUDED.auth_mode,
                    encrypted_credentials = EXCLUDED.encrypted_credentials,
                    updated_at = NOW()
                """,
                (user_id, auth_mode, encrypted_credentials),
            )
        conn.commit()


def get_groww_connection(user_id: str) -> dict[str, Any] | None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, auth_mode, encrypted_credentials,
                       created_at, updated_at
                FROM groww_connections
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()

    if row is None:
        return None

    return {
        "user_id": row[0],
        "auth_mode": row[1],
        "encrypted_credentials": row[2],
        "created_at": row[3],
        "updated_at": row[4],
    }


def delete_groww_connection(user_id: str) -> bool:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM groww_connections WHERE user_id = %s",
                (user_id,),
            )
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted
