# ArthaVani

ArthaVani is a real-time voice finance assistant built around LangGraph, native Python finance tools, Deepgram speech recognition, Silero VAD, WebRTC echo cancellation, and Edge TTS.

The web application has two runtime pieces:

```text
Browser (React + Vite)
  -> FastAPI REST + WebSocket API
  -> LangGraph + native finance tools
  -> Groww / Yahoo Finance / AMFI / FX providers
  -> PostgreSQL conversation checkpoints

Browser microphone
  -> VAD / AEC / Deepgram STT
  -> LangGraph agent
  -> Edge TTS
  -> Browser speaker
```

Finance providers live under `finance_agent/providers/` and are exposed to LangGraph through `finance_agent/tools.py`.

## Requirements

- Python 3.11+
- Node.js 22+
- Docker + Docker Compose (for local PostgreSQL)
- API credentials for the services you plan to use: Groq, Deepgram, and Groww

## 1. Clone and create the Python environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

On Windows PowerShell:

```powershell
.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` installs the runtime, API, test, lint, and formatting dependencies.

## 2. Start PostgreSQL

```bash
docker compose up -d postgres
docker compose ps
```

PostgreSQL is exposed at `localhost:5432` with the development credentials from `docker-compose.yml`.

## 3. Configure backend environment variables

Copy the example file:

```bash
cp .env.example .env
```

Set at least:

```env
DATABASE_URL=postgresql://arthavani:arthavani@localhost:5432/arthavani
GROQ_API_KEY=...
DEEPGRAM_API_KEY=...
API_JWT_SECRET_KEY=...
GROWW_CREDENTIALS_ENCRYPTION_KEY=...
```

Generate the Fernet key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`API_CORS_ORIGINS` should include the Vite development origin, for example:

```env
API_CORS_ORIGINS=["http://localhost:5173"]
```

## 4. Start the FastAPI backend

From the repository root:

```bash
source .venv/bin/activate
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

The API is then available at `http://127.0.0.1:8000` and the browser voice WebSocket is served by the same FastAPI process.

> `python main.py` starts the lower-level local `VoicePipeline` entry point. For the full React + FastAPI web application, use `uvicorn api.main:app` as shown above.

## 5. Configure and start the frontend

In a second terminal:

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

The Vite app runs at `http://localhost:5173` and proxies `/api` and WebSocket traffic to the FastAPI backend on port 8000.

If `package.json` has changed after pulling the repository, run `npm install` once so `package-lock.json` is refreshed before using `npm ci` in other environments.

## 6. Typical local workflow

```text
Terminal 1: docker compose up -d postgres
Terminal 2: uvicorn api.main:app --reload --port 8000
Terminal 3: cd frontend && npm install && npm run dev
Browser:   http://localhost:5173
```

After registering, connect Groww from the UI. Groww credentials are encrypted before storage and are not returned to the browser after a successful connection.

## Testing

Run the backend tests:

```bash
pytest -q
```

The PostgreSQL persistence test is skipped unless `DATABASE_URL` is configured. To exercise it explicitly:

```bash
DATABASE_URL=postgresql://arthavani:arthavani@localhost:5432/arthavani pytest -q tests/test_postgres_persistence.py
```

The repository also contains deterministic evaluation suites under `evaluation/` for tool routing and answer grounding. Their checked-in result files document the benchmark runs used during development.

## Code quality

Python formatting and linting:

```bash
black api config finance_agent voice tests main.py
ruff check api config finance_agent voice tests main.py
```

React linting and formatting:

```bash
cd frontend
npm run lint
npm run format
npm run format:check
```

CI runs the test suite, Python compile checks, Ruff, Black formatting checks, React linting, Prettier formatting checks, and the Vite production build.

## Repository structure

```text
api/
  main.py             # FastAPI app, REST endpoints, and browser voice WebSocket
  dashboard.py        # dashboard aggregation endpoint
  groww.py            # authenticated Groww connection lifecycle
  security.py         # password hashing and JWT authentication
  rate_limit.py       # registration/login rate limiting

finance_agent/
  graph.py            # LangGraph state graph
  runner.py           # async agent runner + PostgreSQL checkpointing
  tools.py            # LLM-facing native tools
  providers/          # Groww, Yahoo, AMFI, FX, market, and watchlist providers

voice/
  audio/              # microphone, speaker, resampling, AEC
  llm/                # conversation-to-agent bridge
  stt/                # Deepgram streaming STT
  text/               # streaming sentence splitting
  tts/                # Edge TTS
  vad/                # Silero speech detection

frontend/src/
  App.jsx             # session bootstrap and route orchestration
  pages/              # auth and Groww connection screens
  components/         # dashboard cards and live assistant UI
  utils/              # shared formatting / URL helpers
```
