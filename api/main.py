"""FastAPI HTTP API for ArthaVani."""
from __future__ import annotations

from api.dashboard import dashboard_endpoint

import uuid
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm

from api.groww import connect_once, disconnect, get_status
from api.schemas import (
    ChatRequest,
    ChatResponse,
    GrowwConnectRequest,
    GrowwConnectionResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from api.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from config.logger import logger
from config.settings import settings
from finance_agent.persistence import create_user, get_user_by_email, initialize_database
from finance_agent.runner import FinanceAgentRunner
from finance_agent.user_context import user_scope
from finance_agent.providers.groww import build_groww_provider_from_credentials
from finance_agent.tools import get_portfolio_summary


runner = FinanceAgentRunner()


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    await runner.start()
    logger.info("ArthaVani FastAPI backend started.")
    try:
        yield
    finally:
        await runner.stop()
        logger.info("ArthaVani FastAPI backend stopped.")


app = FastAPI(
    title="ArthaVani API",
    version="1.0.0",
    description=(
        "Authenticated API for the ArthaVani finance and voice-agent backend."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.API_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


CurrentUser = Annotated[dict, Depends(get_current_user)]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/v1/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(payload: RegisterRequest) -> UserResponse:
    email = payload.email.lower().strip()

    if get_user_by_email(email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user_id = str(uuid.uuid4())
    try:
        user = create_user(
            user_id=user_id,
            email=email,
            password_hash=hash_password(payload.password.get_secret_value()),
        )
    except Exception as exc:
        logger.exception("Failed to create user.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create the account.",
        ) from exc

    return UserResponse(
        id=user["id"],
        email=user["email"],
        created_at=user["created_at"],
    )


@app.post("/api/v1/auth/token", response_model=TokenResponse)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
    email = form.username.lower().strip()
    user = get_user_by_email(email)

    if user is None or not verify_password(
        form.password,
        user["password_hash"],
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token(user["id"]),
        token_type="bearer",
    )


@app.get("/api/v1/auth/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse(
        id=user["id"],
        email=user["email"],
        created_at=user["created_at"],
    )


@app.get(
    "/api/v1/integrations/groww",
    response_model=GrowwConnectionResponse,
)
async def groww_status(user: CurrentUser) -> GrowwConnectionResponse:
    return GrowwConnectionResponse(**get_status(user["id"]))


@app.post(
    "/api/v1/integrations/groww/connect",
    response_model=GrowwConnectionResponse,
)
async def groww_connect(
    payload: GrowwConnectRequest,
    user: CurrentUser,
) -> GrowwConnectionResponse:
    if payload.auth_mode == "api_key_secret":
        if payload.api_key is None or payload.api_secret is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="api_key and api_secret are required for api_key_secret mode.",
            )
        credentials = {
            "api_key": payload.api_key.get_secret_value(),
            "api_secret": payload.api_secret.get_secret_value(),
        }

    else:
        if payload.totp_token is None or payload.totp_secret is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="totp_token and totp_secret are required for totp mode.",
            )
        credentials = {
            "totp_token": payload.totp_token.get_secret_value(),
            "totp_secret": payload.totp_secret.get_secret_value(),
        }

    # Verify the credentials against Groww before persisting them.
    try:
        groww = build_groww_provider_from_credentials(
            payload.auth_mode,
            credentials,
        )
        groww.get_holdings()
    except Exception as exc:
        logger.warning(
            "Groww connection validation failed for user=%s: %s",
            user["id"],
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Groww credentials could not be validated.",
        ) from exc

    result = connect_once(
        user_id=user["id"],
        auth_mode=payload.auth_mode,
        credentials=credentials,
    )
    return GrowwConnectionResponse(**result)


@app.delete("/api/v1/integrations/groww", status_code=status.HTTP_204_NO_CONTENT)
async def groww_disconnect(user: CurrentUser) -> None:
    disconnect(user["id"])


@app.get("/api/v1/portfolio/summary")
async def portfolio_summary(user: CurrentUser) -> dict:
    with user_scope(user["id"]):
        return await get_portfolio_summary.ainvoke({})


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, user: CurrentUser) -> ChatResponse:
    thread_id = (
        f"user:{user['id']}:conversation:{payload.conversation_id}"
    )

    with user_scope(user["id"]):
        answer = await runner.ainvoke(
            payload.message,
            thread_id=thread_id,
        )

    return ChatResponse(
        message=answer,
        conversation_id=payload.conversation_id,
    )


@app.get("/api/v1")
async def api_root() -> dict[str, str]:
    return {"name": "ArthaVani API", "version": "1.0.0"}

@app.get("/api/v1/dashboard")
async def dashboard(user: CurrentUser):
    return await dashboard_endpoint(user)
