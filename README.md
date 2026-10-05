# ArthaVani

**ArthaVani** is a voice-first personal finance and market-research assistant for Indian markets.

It combines a React dashboard, FastAPI backend, LangGraph finance agent, Groww portfolio integration, market-data providers, and a real-time browser voice pipeline.

> **Live demo:** [Open ArthaVani](https://arthavani-1.onrender.com/)

## What it solves

Instead of switching between a broker, market-data sites, news pages and calculators, users can ask portfolio and market questions in one place.

```text
What is my portfolio worth right now?
What is my total P&L?
How concentrated is my portfolio?
What is my largest holding?
What is TCS doing today?
What is the latest news on INFY?
What is the RSI of RELIANCE?
Is the NSE market open right now?
```

> ArthaVani is a research/analysis tool, not personalized investment advice.

## Questions worth asking about a portfolio

- What are my invested value, current value and total P&L?
- Which holdings drive most of my gains or losses?
- What are the weights of my largest positions?
- How concentrated is the portfolio?
- Am I overly dependent on one company, sector or theme?
- Are my prices live, delayed or fallback values?

# Architecture

```text
React / Vite
   │
   ├── REST ───────────────┐
   └── WebSocket (voice) ──┤
                           ▼
                     FastAPI backend
                           │
                       user_id
                           ▼
                     LangGraph agent
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
      Groww            Yahoo / AMFI         FX / NSE
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ▼
                  PostgreSQL / SQLite
```

Text and voice use the same finance-agent core.

# Voice pipeline

```text
Microphone
   ↓
AudioWorklet / SoundDevice
   ↓
16 kHz mono PCM s16le
   ↓
WebSocket / local audio queues
   ├── Silero VAD
   └── Deepgram streaming STT
            ↓
       final transcript
            ↓
        LLM Worker
            ↓
        LangGraph
            ↓
      finance tool calls
            ↓
       streamed text
            ↓
    sentence segmentation
            ↓
         Edge TTS
            ↓
        PCM audio
            ↓
      browser / speaker
```

## Audio format and buffering

After the capture boundary, the application uses one common format:

| Item | Value |
|---|---:|
| Sample rate | 16 kHz |
| Channels | Mono |
| Sample format | signed 16-bit PCM |
| Bytes/sample | 2 |
| VAD frame | 512 samples = 32 ms |
| STT/TTS batch | 3,200 bytes = 100 ms |

Useful conversions:

```text
20 ms  = 320 samples  = 640 bytes
32 ms  = 512 samples  = 1,024 bytes
100 ms = 1,600 samples = 3,200 bytes
```

Desktop capture is typically **44.1 kHz** and is resampled to 16 kHz with `scipy.signal.resample_poly` before entering the common pipeline.

The browser worklet converts browser audio to 16 kHz int16 PCM and sends about **20 ms chunks**.

Bounded `asyncio.Queue`s connect the stages so temporary downstream slowdowns do not create unbounded memory growth.

## VAD and interruption

Silero VAD consumes exact 512-sample frames. A small state machine turns frame probabilities into speech-start and speech-end events.

When the user starts talking while ArthaVani is speaking:

```text
speech detected
      ↓
duck / stop playback
      ↓
cancel active generation
      ↓
clear buffered assistant audio
      ↓
process the new user turn
```

The browser also uses interim STT information to make barge-in responsive.

## Streaming TTS

The LLM is streamed instead of waiting for the full response:

```text
LLM chunks → sentence splitter → Edge TTS → audio chunks
```

This lets the first sentence start playing while later sentences are still being generated.

# LangGraph agent

```text
User message
    ↓
normalize/history
    ↓
keyword-based tool routing
    ↓
small relevant tool set
    ↓
Groq model
    ↓
optional tool calls
    ↓
tool results
    ↓
grounded final answer
```

### Why keyword routing?

There are only a small number of lightweight, non-identical finance tools. Selecting a relevant subset before the model call reduces prompt/tool overhead and helps voice latency.

The router is an optimization, not the source of truth:

```text
clear match → narrow tool group
ambiguous → broader fallback set
```

## Finance tools

**Portfolio**
- Summary
- Risk / concentration

**Market research**
- Quote
- Fundamentals
- History
- Technical analysis
- News
- Corporate actions
- Earnings calendar

**Other**
- AMFI NAV
- Currency conversion
- NSE market status
- SQLite watchlist

## User-scoped execution

The authenticated identity flows through the complete finance stack:

```text
JWT / WebSocket auth
        ↓
      user_id
        ↓
   LangGraph state
        ↓
InjectedState("user_id")
        ↓
user-scoped Groww / watchlist access
```

# Data, storage and security

### PostgreSQL

Used for durable/shared application state and LangGraph conversation checkpoints:

- users
- Groww connection metadata
- encrypted Groww credentials
- conversation checkpoints

### SQLite

The watchlist intentionally remains SQLite because it is a tiny, simple per-user dataset.

For multi-instance production deployments, use persistent/shared storage or move the watchlist to PostgreSQL.

### Security

- JWT authentication
- Argon2 password hashing
- Fernet encryption for stored Groww credentials
- user-scoped portfolio/watchlist access
- authenticated voice WebSocket

# Repository layout

```text
ArthaVani/
├── api/
│   ├── main.py              # FastAPI app, REST + voice WebSocket
│   ├── dashboard.py         # Dashboard aggregation
│   ├── groww.py             # Groww connection lifecycle
│   ├── schemas.py           # API models
│   ├── security.py          # Auth/JWT/password helpers
│   └── rate_limit.py        # Auth rate limiting
│
├── config/
│   ├── settings.py          # Environment configuration
│   ├── constants.py         # Audio/VAD/queue constants
│   └── logger.py             # Logging
│
├── finance_agent/
│   ├── graph.py             # LangGraph graph, prompt, routing
│   ├── runner.py            # Agent lifecycle + streaming
│   ├── tools.py             # Finance tools
│   ├── persistence.py       # PostgreSQL persistence
│   ├── conversation.py      # User/thread identity
│   ├── groww_credentials.py # Groww credential encryption
│   └── providers/           # Groww, Yahoo, AMFI, FX, NSE, watchlist
│
├── voice/
│   ├── web_pipeline.py      # Browser voice/WebSocket
│   ├── pipeline.py          # Local voice pipeline
│   ├── audio/               # Capture, resampling, playback, AEC
│   ├── vad/                 # Silero VAD
│   ├── stt/                 # Deepgram STT
│   ├── llm/                 # Transcript → agent
│   ├── text/                # Sentence splitting
│   └── tts/                 # Edge TTS/audio conversion
│
├── frontend/
│   ├── src/                 # React app, pages, components, API client
│   └── public/              # AudioWorklet scripts
│
├── tests/                   # Unit/integration/voice tests
├── evaluation/              # Tool-routing + grounding evaluation
├── scripts/                 # Manual provider/LLM checks
├── .github/workflows/       # GitHub Actions CI
├── docker-compose.yml       # Local PostgreSQL
├── render.yaml              # Render deployment
├── requirements*.txt        # Python dependencies
└── run_voice.py             # Local voice entrypoint
```

# Tech stack

| Layer | Technologies |
|---|---|
| Frontend | React 19, React Router, Vite, AudioWorklet, WebSocket |
| Backend | Python 3.11, FastAPI, Uvicorn, Pydantic |
| Auth | JWT, Argon2, Fernet |
| Agent | LangGraph, LangChain Core, Groq |
| Voice | Deepgram, Silero VAD, Edge TTS, PyAV, SciPy, SoundDevice |
| Finance | Groww, Yahoo Finance, AMFI, FX provider, NSE logic |
| Storage | PostgreSQL, SQLite |
| DevOps | Docker Compose, GitHub Actions, Render |

# API surface

```text
GET    /health
POST   /api/v1/auth/register
POST   /api/v1/auth/token
GET    /api/v1/auth/me

GET    /api/v1/integrations/groww
POST   /api/v1/integrations/groww/connect
PUT    /api/v1/integrations/groww
DELETE /api/v1/integrations/groww

GET    /api/v1/portfolio/summary
GET    /api/v1/dashboard
POST   /api/v1/chat
WS     /api/v1/voice
```

FastAPI docs locally:

```text
http://127.0.0.1:8000/docs
```

# Requirements

- Python 3.11
- Node.js 22+
- PostgreSQL 16+
- Docker (recommended for local PostgreSQL)
- Browser with microphone + AudioWorklet support for browser voice
- API credentials for the providers you use

## Environment

```bash
cp .env.example .env
```

Typical backend settings:

```env
DATABASE_URL=postgresql://arthavani:arthavani@localhost:5432/arthavani
GROQ_API_KEY=...
GROQ_MODEL=...
DEEPGRAM_API_KEY=...
DEEPGRAM_MODEL=nova-3
API_JWT_SECRET_KEY=...
API_JWT_ALGORITHM=HS256
API_JWT_EXPIRE_MINUTES=60
API_CORS_ORIGINS=["http://localhost:5173"]
GROWW_CREDENTIALS_ENCRYPTION_KEY=...
```

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Never commit real secrets.

# Getting started

## 1. Clone and install

```bash
git clone https://github.com/31groot/ArthaVani.git
cd ArthaVani

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## 2. Start PostgreSQL

```bash
docker compose up -d postgres
docker compose ps
```

Default local connection:

```text
postgresql://arthavani:arthavani@localhost:5432/arthavani
```

## 3. Configure the backend

```bash
cp .env.example .env
```

Set the required API keys and database/security settings.

## 4. Start the backend

```bash
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Check it:

```bash
curl http://127.0.0.1:8000/health
```

## 5. Start the frontend

```bash
cd frontend
cp .env.example .env
npm ci
npm run dev
```

Local frontend:

```text
http://127.0.0.1:5173
```

For an explicit backend origin:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_VOICE_WS_URL=ws://127.0.0.1:8000
```

Production uses `https://` + `wss://`.

# Useful development commands

```bash
# PostgreSQL
docker compose up -d postgres

# Backend
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000

# Tests
pytest -q

# Python compile check
python -m compileall api config finance_agent voice tests

# Dependency check
pip check

# Git hygiene
git diff --check
```

Frontend, from `frontend/`:

```bash
npm ci
npm run dev
npm run build
npm run preview
```

Local native voice:

```bash
python run_voice.py
```

# Testing

Run everything:

```bash
pytest -q
```

The current development baseline is **40 passing tests** covering agent behavior, routing, persistence, VAD/STT, text splitting and provider logic.

Evaluation assets live under:

```text
evaluation/BFCL/
evaluation/answer_grounding/
```

# CI and deployment

GitHub Actions is defined in:

```text
.github/workflows/ci-cd.yml
```

CI runs backend tests against PostgreSQL and builds the frontend.

Render uses two services:

```text
Frontend static service
        ↓
React/Vite

Backend web service
        ↓
FastAPI + Uvicorn
        ↓
PostgreSQL + external providers
```

Production frontend variables:

```env
VITE_API_BASE_URL=https://<backend-host>
VITE_VOICE_WS_URL=wss://<backend-host>
```

The backend CORS configuration must allow the frontend origin.

# Design priorities

### Realtime where it matters

Portfolio values and current quotes are fetched fresh when providers support it. Slower-changing data can use different freshness policies.

### Low-latency voice

Small PCM chunks, bounded queues, streaming STT, streamed LLM output, sentence-level TTS and barge-in handling are used to reduce perceived latency.

### Lightweight state

PostgreSQL handles durable/shared state. SQLite remains the intentionally lightweight watchlist store.

### Grounded finance answers

Tools return data plus source/freshness context where available, and the agent is instructed not to present delayed/fallback data as live.

# Current tradeoffs

- SQLite watchlist persistence depends on the deployment filesystem.
- External finance/voice providers can fail or return delayed data.
- Voice latency depends on network, browser audio behavior and provider response time.