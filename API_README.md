# ArthaVani FastAPI + Auth + User-Scoped Groww

This adds an HTTP layer around the existing finance agent.

## Architecture

```text
Client
  -> FastAPI
      -> JWT authentication
      -> per-user context
      -> LangGraph / finance tools
          -> user-scoped Groww credentials
          -> Yahoo / AMFI / FX / NSE / watchlist
      -> PostgreSQL
          -> users
          -> encrypted Groww connection
          -> LangGraph conversation checkpoints
```

Groww credentials are encrypted before they are stored. They are never
returned by the API.

## Authentication

`POST /api/v1/auth/register`

`POST /api/v1/auth/token`

The token endpoint follows FastAPI's OAuth2 bearer-token convention.

## Groww connection

`POST /api/v1/integrations/groww/connect`

The connection is deliberately one-time per user. If a user already has a
Groww connection, the endpoint returns HTTP 409 instead of silently replacing
it.

Two Groww modes are supported:

1. `api_key_secret`
2. `totp`

The TOTP route is preferable when the goal is to avoid re-entering Groww
credentials: Groww documents its TOTP token flow as having no expiry. The API
key + secret flow still follows Groww's requirement for daily approval.

## Example TOTP payload

```json
{
  "auth_mode": "totp",
  "totp_token": "YOUR_TOTP_TOKEN",
  "totp_secret": "YOUR_TOTP_SECRET"
}
```

## Example API-key payload

```json
{
  "auth_mode": "api_key_secret",
  "api_key": "YOUR_API_KEY",
  "api_secret": "YOUR_API_SECRET"
}
```

The server first validates the credentials against Groww, then encrypts and
persists them.

## Chat

`POST /api/v1/chat`

```json
{
  "message": "What is my portfolio worth?",
  "conversation_id": "default"
}
```

The LangGraph thread ID is derived from the authenticated user and the
conversation ID:

`user:<user_id>:conversation:<conversation_id>`

This prevents one user's persisted conversation from being reused by another.

## Portfolio

`GET /api/v1/portfolio/summary`

The current user's Groww connection is selected automatically.

## Run

Install the normal project requirements and the API additions, set:

- `DATABASE_URL`
- `API_JWT_SECRET_KEY`
- `GROWW_CREDENTIALS_ENCRYPTION_KEY`
- existing Groq / Deepgram variables

Then:

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Open:

`http://127.0.0.1:8000/docs`

## Important

The existing local voice pipeline still uses the machine microphone and
speaker directly. This FastAPI layer exposes the finance-agent backend and
HTTP chat. A browser/mobile WebSocket audio transport is a separate step.


## One-time connection semantics

The ArthaVani API stores the user's Groww credentials encrypted at rest and refuses a second connection for the same user until the existing connection is explicitly disconnected. With Groww's TOTP mode, Groww documents the TOTP token as having no expiry; with the API-key/secret mode, Groww still requires daily approval on its Cloud API Keys page, so the app cannot remove that Groww-side requirement.
