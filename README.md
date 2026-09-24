# ArthaVani

ArthaVani is a full-stack AI finance assistant for Indian markets. It combines a FastAPI backend, a React dashboard, LangGraph, native Python finance tools, PostgreSQL conversation persistence, authenticated Groww connections, streaming speech recognition, Silero VAD, Edge TTS, and a browser voice transport built on WebSockets.

The project is designed to support two voice modes:

- **Desktop/local voice:** microphone and speaker devices are handled directly by the Python voice pipeline.
- **Browser voice:** the React app captures microphone audio with `AudioWorklet`, streams PCM audio over a WebSocket to FastAPI, and receives synthesized PCM audio back for browser playback.

WebRTC audio processing is used for echo-cancellation/noise-processing support in the Python audio stack; the browser transport itself is a WebSocket transport, not a WebRTC peer connection.

---

## Architecture

```text
                         ArthaVani
                            │
             ┌──────────────┴──────────────┐
             │                             │
       React + Vite                    FastAPI
             │                             │
       REST + WebSocket             Auth / Dashboard
             │                             │
             └──────────────┬──────────────┘
                            │
                    LangGraph agent
                            │
                    Native Python tools
                            │
        ┌───────────────┬───┴────┬───────────────┐
        │               │        │               │
      Groww        Yahoo Finance AMFI          FX / NSE
        │
        └──────────────┬────────────────────────┘
                       │
                 PostgreSQL
          auth + Groww connection metadata
          + LangGraph conversation state

Browser voice:

Microphone
   │
   ▼
AudioWorklet → WebSocket → FastAPI voice session
                              │
                              ├─ Silero VAD
                              ├─ Deepgram streaming STT
                              ├─ LangGraph + finance tools
                              └─ Edge TTS
                                      │
                                      ▼
                              WebSocket PCM audio
                                      │
                                      ▼
                              Browser AudioWorklet
```

---

## Main capabilities

### Finance assistant

The agent can work with:

- portfolio summary and portfolio risk
- live/near-current Indian equity quotes
- company fundamentals
- historical prices
- technical analysis
- market and ticker news
- AMFI mutual-fund NAVs and NAV history
- currency conversion
- NSE market status
- persistent, user-scoped price alerts

The LLM-facing finance tools are implemented as native Python tools in `finance_agent/tools.py` rather than through MCP.

When Groww live market quotes are unavailable, the portfolio flow can use an explicitly labelled Yahoo Finance fallback for valuation. The tool output keeps the price source visible instead of presenting fallback data as Groww live data.

### Authentication and user data

The FastAPI layer provides:

- account registration and login
- JWT authentication
- password hashing with Argon2 via `pwdlib`
- authenticated REST endpoints
- authenticated browser voice sessions
- per-user Groww connections
- encrypted Groww credentials at rest using Fernet

Groww credentials are stored server-side and are not returned to the browser after a successful connection.

### Conversation memory

LangGraph conversation state is persisted with PostgreSQL through `AsyncPostgresSaver`.

Conversation identity is scoped as:

```text
user:{user_id}:conversation:{conversation_id}
```

This keeps conversation history separated by authenticated user and conversation.

Local price alerts use a separate SQLite store and are scoped to the authenticated user.

---

## Requirements

- Python 3.11+
- Node.js 22+
- PostgreSQL 16+ or Docker Desktop / Docker Engine
- API credentials for the services you intend to use

Typical backend credentials include:

```text
GROQ_API_KEY
DEEPGRAM_API_KEY
API_JWT_SECRET_KEY
GROWW_CREDENTIALS_ENCRYPTION_KEY
```

Groww credentials are supplied through the authenticated UI rather than committed to `.env`.

---

## 1. Clone the repository

```bash
git clone https://github.com/31groot/ArthaVani.git
cd ArthaVani
```

Create and activate the Python environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

---

## 2. Start PostgreSQL

The repository includes a development Docker Compose configuration:

```bash
docker compose up -d postgres
docker compose ps
```

The development database is exposed on:

```text
localhost:5432
```

with:

```text
Database: arthavani
User:     arthavani
Password: arthavani
```

A local PostgreSQL installation can also be used; point `DATABASE_URL` at it instead.

---

## 3. Configure the backend

Copy the example environment file:

```bash
cp .env.example .env
```

At minimum, configure:

```env
DATABASE_URL=postgresql://arthavani:arthavani@localhost:5432/arthavani
GROQ_API_KEY=...
DEEPGRAM_API_KEY=...
API_JWT_SECRET_KEY=...
GROWW_CREDENTIALS_ENCRYPTION_KEY=...
```

Generate a Fernet encryption key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

For local frontend development, allow the Vite origin:

```env
API_CORS_ORIGINS=["http://localhost:5173"]
```

Do not commit `.env` or real API credentials.

---

## 4. Start the backend

From the repository root:

```bash
source .venv/bin/activate
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

The FastAPI API is available at:

```text
http://127.0.0.1:8000
```

Interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

The browser voice WebSocket is exposed by the same FastAPI process at:

```text
/api/v1/voice
```

For the lower-level local Python voice application, `main.py` starts `VoicePipeline` directly:

```bash
python main.py
```

That entry point uses the local microphone/speaker pipeline and is separate from the React browser transport.

---

## 5. Start the frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The Vite development server normally runs at:

```text
http://localhost:5173
```

The frontend reads the backend URL from `frontend/.env` when `VITE_API_BASE_URL` is provided. The default example is:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

For local browser voice, use a browser with microphone and AudioWorklet support, such as current Chrome or Edge. Microphone access requires a secure context in production; `localhost` is suitable for local development.

---

## 6. First-run flow

```text
Register / sign in
        ↓
Connect Groww once
        ↓
Dashboard
        ↓
Portfolio + market data + news
        ↓
Ask ArthaVani by text or live voice
```

After a successful Groww connection, the encrypted credentials remain on the backend so the user does not have to reconnect on every login.

---

## Browser voice pipeline

The current browser voice implementation is intentionally simpler than a browser WebRTC deployment.

```text
Browser microphone
       ↓
AudioWorklet PCM capture
       ↓
Authenticated WebSocket
       ↓
FastAPI browser voice session
       ↓
Silero VAD + Deepgram STT
       ↓
LangGraph + native finance tools
       ↓
Sentence splitter + Edge TTS
       ↓
PCM audio over WebSocket
       ↓
Browser AudioWorklet playback
```

The browser and server exchange control messages for events such as:

- authentication
- readiness
- interim transcript
- final user text
- assistant text
- TTS start/finish
- duck/unduck
- barge-in
- playback drain
- errors

Barge-in is handled on the server and client together so user speech can cut off buffered assistant audio and interrupt the active LLM/TTS work.

---

## API surface

Important REST endpoints include:

```text
GET    /health
POST   /api/v1/auth/register
POST   /api/v1/auth/token
GET    /api/v1/auth/me
GET    /api/v1/integrations/groww
POST   /api/v1/integrations/groww/connect
DELETE /api/v1/integrations/groww
GET    /api/v1/portfolio/summary
POST   /api/v1/chat
GET    /api/v1/dashboard
```

Browser voice:

```text
WebSocket /api/v1/voice
```

Use `/docs` for the generated OpenAPI documentation and request schemas.

---

## Testing

Run the complete backend test suite:

```bash
source .venv/bin/activate
pytest -q
```

Compile-check the Python packages:

```bash
python -m compileall api config finance_agent voice tests main.py
```

Check whitespace before committing:

```bash
git diff --check
```

The repository also contains deterministic evaluation suites under `evaluation/` for tool routing and answer grounding.

---

## Frontend build

Create a production frontend bundle with:

```bash
cd frontend
npm install
npm run build
```

The generated static files are written to:

```text
frontend/dist/
```

---

## CI

GitHub Actions is defined in:

```text
.github/workflows/ci-cd.yml
```

The current workflow runs on pushes and pull requests targeting `main` and performs:

1. PostgreSQL-backed backend dependency installation
2. `pip check`
3. Python compilation checks
4. the backend `pytest` suite
5. React dependency installation with `npm ci`
6. the Vite production build
7. upload of the frontend `dist/` directory as a build artifact for `main` pushes

---

## Repository layout

```text
ArthaVani/
├── api/
│   ├── main.py              # FastAPI app and REST/WebSocket routes
│   ├── dashboard.py         # dashboard aggregation
│   ├── groww.py             # Groww connection lifecycle
│   ├── security.py          # password hashing and JWT handling
│   └── rate_limit.py        # auth rate limiting
│
├── config/
│   ├── constants.py         # audio/runtime constants
│   ├── logger.py            # logging setup
│   └── settings.py          # environment-backed settings
│
├── finance_agent/
│   ├── graph.py             # LangGraph state graph
│   ├── runner.py            # agent runner + PostgreSQL checkpointing
│   ├── tools.py             # native LLM-facing finance tools
│   ├── persistence.py       # users + Groww connection persistence
│   ├── groww_credentials.py # encrypted Groww credentials
│   └── providers/            # Groww, Yahoo, AMFI, FX, market, watchlist
│
├── voice/
│   ├── audio/               # microphone, speaker, resampling, AEC
│   ├── llm/                 # transcript → agent bridge
│   ├── stt/                 # Deepgram streaming STT
│   ├── text/                # sentence splitting
│   ├── tts/                 # Edge TTS
│   ├── vad/                 # Silero speech detection
│   ├── pipeline.py          # local/native voice pipeline
│   └── web_pipeline.py      # browser WebSocket voice pipeline
│
├── frontend/
│   ├── src/pages/            # auth, dashboard, Groww screens
│   ├── src/components/       # dashboard + assistant UI
│   ├── public/               # audio capture/playback worklets
│   └── src/api.js            # REST/WebSocket client helpers
│
├── evaluation/
│   ├── BFCL/                # tool-routing evaluation
│   └── answer_grounding/    # answer-grounding evaluation
│
├── tests/                   # unit, integration, API, voice tests
├── docker-compose.yml       # local PostgreSQL
├── requirements.txt         # runtime dependencies
├── requirements-dev.txt     # runtime + development/test dependencies
└── main.py                  # native/local voice entry point
```

---

## Security notes

- Passwords are hashed; plaintext passwords are not stored.
- Groww credentials are encrypted at rest before database persistence.
- API routes require JWT authentication where appropriate.
- Browser voice authenticates its WebSocket session with the access token before processing audio.
- Never commit `.env`, API keys, JWT signing secrets, Groww credentials, or database passwords for shared environments.
- Replace the development PostgreSQL credentials before exposing the database outside a local development environment.

---

## Useful development commands

```bash
# Backend
source .venv/bin/activate
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000

# Tests
pytest -q

# Frontend
cd frontend
npm install
npm run dev

# Production frontend build
npm run build
```

---

## Project status

ArthaVani currently combines a working authenticated web dashboard with a native finance-agent backend, PostgreSQL-backed conversation memory, authenticated Groww integration, deterministic evaluation suites, and a real-time browser voice path based on WebSocket streaming audio.

The repository is intended as an AI engineering project demonstrating agent orchestration, tool calling, real-time voice processing, persistence, authentication, provider integration, evaluation, and full-stack delivery.