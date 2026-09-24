"""FastAPI HTTP API for ArthaVani."""
from __future__ import annotations

from api.dashboard import dashboard_endpoint

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm

from api.groww import connect_once, disconnect, get_status, replace_connection
from api.rate_limit import client_ip, login_limiter, register_limiter
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
    aget_user_from_access_token,
    hash_password,
    verify_password,
)
from config.logger import logger
from config.settings import settings
from finance_agent.persistence import (
    close_pool,
    create_user,
    get_user_by_email,
    initialize_database,
)
from finance_agent.runner import FinanceAgentRunner
from finance_agent.user_context import user_scope
from finance_agent.providers.groww import build_groww_provider_from_credentials
from finance_agent.tools import get_portfolio_summary
from voice.web_pipeline import run_browser_voice_session


runner = FinanceAgentRunner()

# Only one browser voice session may own a given user/conversation at a time.
# This prevents duplicate WebSocket sessions after refreshes/double clicks from
# running two STT/LLM/TTS pipelines against the same persisted conversation.
_active_voice_sessions: dict[tuple[str, str], WebSocket] = {}
_active_voice_sessions_lock = asyncio.Lock()


async def _claim_voice_session(
    user_id: str,
    conversation_id: str,
    websocket: WebSocket,
) -> None:
    key = (user_id, conversation_id)
    old_socket = None

    async with _active_voice_sessions_lock:
        old_socket = _active_voice_sessions.get(key)
        _active_voice_sessions[key] = websocket

    if old_socket is not None and old_socket is not websocket:
        logger.info(
            "Replacing existing browser voice session for user=%s conversation=%s.",
            user_id,
            conversation_id,
        )
        try:
            await old_socket.close(code=4001, reason="Replaced by a newer voice session.")
        except Exception:
            logger.debug("Previous browser voice socket was already closed.", exc_info=True)


async def _release_voice_session(
    user_id: str,
    conversation_id: str,
    websocket: WebSocket,
) -> None:
    key = (user_id, conversation_id)
    async with _active_voice_sessions_lock:
        if _active_voice_sessions.get(key) is websocket:
            _active_voice_sessions.pop(key, None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    await runner.start()
    logger.info("ArthaVani FastAPI backend started.")
    try:
        yield
    finally:
        await runner.stop()
        close_pool()
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
async def register(payload: RegisterRequest, request: Request) -> UserResponse:
    email = payload.email.lower().strip()
    limiter_key = f"{client_ip(request)}:{email}"
    register_limiter.check(limiter_key)

    if await asyncio.to_thread(get_user_by_email, email) is not None:
        register_limiter.record_failure(limiter_key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user_id = str(uuid.uuid4())
    try:
        user = await asyncio.to_thread(
            create_user,
            user_id=user_id,
            email=email,
            password_hash=hash_password(payload.password.get_secret_value()),
        )
    except Exception as exc:
        logger.exception("Failed to create user.")
        register_limiter.record_failure(limiter_key)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create the account.",
        ) from exc

    register_limiter.record_success(limiter_key)
    return UserResponse(
        id=user["id"],
        email=user["email"],
        created_at=user["created_at"],
    )


@app.post("/api/v1/auth/token", response_model=TokenResponse)
async def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
    email = form.username.lower().strip()
    limiter_key = f"{client_ip(request)}:{email}"
    login_limiter.check(limiter_key)

    user = await asyncio.to_thread(get_user_by_email, email)

    if user is None or not verify_password(
        form.password,
        user["password_hash"],
    ):
        login_limiter.record_failure(limiter_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    login_limiter.record_success(limiter_key)
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
    result = await asyncio.to_thread(get_status, user["id"])
    return GrowwConnectionResponse(**result)


def _extract_groww_credentials(payload: GrowwConnectRequest) -> dict[str, str]:
    """Shared validation/extraction for connect and replace payloads."""
    if payload.auth_mode == "api_key_secret":
        if payload.api_key is None or payload.api_secret is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="api_key and api_secret are required for api_key_secret mode.",
            )
        return {
            "api_key": payload.api_key.get_secret_value(),
            "api_secret": payload.api_secret.get_secret_value(),
        }

    if payload.totp_token is None or payload.totp_secret is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="totp_token and totp_secret are required for totp mode.",
        )
    return {
        "totp_token": payload.totp_token.get_secret_value(),
        "totp_secret": payload.totp_secret.get_secret_value(),
    }


def _validate_groww_credentials_sync(
    auth_mode: str,
    credentials: dict[str, str],
) -> None:
    """Blocking network call to Groww to confirm the credentials work."""
    groww = build_groww_provider_from_credentials(auth_mode, credentials)
    groww.get_holdings()


async def _validate_groww_credentials(
    user_id: str,
    auth_mode: str,
    credentials: dict[str, str],
    *,
    on_failure_detail: str,
) -> None:
    """Validate credentials against Groww off the event loop, or raise 400."""
    try:
        await asyncio.to_thread(
            _validate_groww_credentials_sync, auth_mode, credentials
        )
    except Exception as exc:
        logger.warning(
            "Groww credential validation failed for user=%s: %s",
            user_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=on_failure_detail,
        ) from exc


@app.post(
    "/api/v1/integrations/groww/connect",
    response_model=GrowwConnectionResponse,
)
async def groww_connect(
    payload: GrowwConnectRequest,
    user: CurrentUser,
) -> GrowwConnectionResponse:
    credentials = _extract_groww_credentials(payload)

    # Verify the credentials against Groww before persisting them.
    await _validate_groww_credentials(
        user["id"],
        payload.auth_mode,
        credentials,
        on_failure_detail="Groww credentials could not be validated.",
    )

    result = await asyncio.to_thread(
        connect_once,
        user_id=user["id"],
        auth_mode=payload.auth_mode,
        credentials=credentials,
    )
    return GrowwConnectionResponse(**result)


@app.put(
    "/api/v1/integrations/groww",
    response_model=GrowwConnectionResponse,
)
async def groww_replace(
    payload: GrowwConnectRequest,
    user: CurrentUser,
) -> GrowwConnectionResponse:
    """Validate and replace the current user's Groww credentials."""
    credentials = _extract_groww_credentials(payload)

    await _validate_groww_credentials(
        user["id"],
        payload.auth_mode,
        credentials,
        on_failure_detail=(
            "New Groww credentials could not be validated. "
            "Existing credentials were kept."
        ),
    )

    result = await asyncio.to_thread(
        replace_connection,
        user_id=user["id"],
        auth_mode=payload.auth_mode,
        credentials=credentials,
    )
    return GrowwConnectionResponse(**result)


@app.delete("/api/v1/integrations/groww", status_code=status.HTTP_204_NO_CONTENT)
async def groww_disconnect(user: CurrentUser) -> None:
    await asyncio.to_thread(disconnect, user["id"])


@app.get("/api/v1/portfolio/summary")
async def portfolio_summary(user: CurrentUser) -> dict:
    with user_scope(user["id"]):
        return await get_portfolio_summary.ainvoke({})


@app.websocket("/api/v1/voice")
async def voice(websocket: WebSocket) -> None:
    """Authenticated full-duplex browser voice transport."""
    await websocket.accept()

    try:
        auth_message = await websocket.receive_json()
    except (WebSocketDisconnect, Exception):
        await websocket.close(code=1008)
        return

    if auth_message.get("type") != "auth":
        await websocket.send_json(
            {"type": "error", "message": "Authentication is required."}
        )
        await websocket.close(code=1008)
        return

    token = auth_message.get("token")
    if not isinstance(token, str) or not token:
        await websocket.send_json(
            {"type": "error", "message": "Authentication token is missing."}
        )
        await websocket.close(code=1008)
        return

    try:
        user = await aget_user_from_access_token(token)
    except HTTPException as exc:
        await websocket.send_json(
            {"type": "error", "message": exc.detail}
        )
        await websocket.close(code=1008)
        return

    conversation_id = auth_message.get("conversation_id", "default")
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        conversation_id = "default"

    await _claim_voice_session(
        user_id=user["id"],
        conversation_id=conversation_id,
        websocket=websocket,
    )

    try:
        await run_browser_voice_session(
            websocket,
            user_id=user["id"],
            conversation_id=conversation_id,
            agent_runner=runner,
        )
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("Browser voice session failed for user=%s", user["id"])
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "Live voice could not start. Check the Deepgram API key and backend logs, then reconnect.",
                }
            )
        except Exception:
            pass
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        await _release_voice_session(
            user_id=user["id"],
            conversation_id=conversation_id,
            websocket=websocket,
        )


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
