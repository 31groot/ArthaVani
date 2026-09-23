"""Pydantic request/response models for the HTTP API."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, SecretStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: SecretStr = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]


class GrowwConnectRequest(BaseModel):
    auth_mode: Literal["api_key_secret", "totp"]

    api_key: SecretStr | None = None
    api_secret: SecretStr | None = None

    totp_token: SecretStr | None = None
    totp_secret: SecretStr | None = None


class GrowwConnectionResponse(BaseModel):
    connected: bool
    auth_mode: Literal["api_key_secret", "totp"] | None = None
    connected_at: datetime | None = None
    updated_at: datetime | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str = Field(default="default", min_length=1, max_length=128)


class ChatResponse(BaseModel):
    message: str
    conversation_id: str
