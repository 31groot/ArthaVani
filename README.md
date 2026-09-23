# ArthaVani

ArthaVani is a real-time voice finance assistant built around LangGraph, native Python finance tools, Deepgram speech recognition, Silero VAD, WebRTC echo cancellation, and Edge TTS.

The current architecture is:

```text
Microphone
  -> VAD / AEC / Deepgram STT
  -> LangGraph + native finance tools
  -> Edge TTS
  -> Speaker
```

The previous MCP-based finance integration has been removed. Finance providers now live directly under `finance_agent/providers/` and are exposed to LangGraph through `finance_agent/tools.py`.

## Conversation persistence

ArthaVani can persist LangGraph conversation state in PostgreSQL using `AsyncPostgresSaver`. The graph stores checkpoints by `thread_id`, so the same configured conversation can resume after the application restarts.

For the async voice pipeline, `AsyncPostgresSaver` is the appropriate checkpointer for async workloads. The first startup calls its `setup()` method to create or migrate the checkpoint tables.

### Start PostgreSQL locally

Docker is the easiest local setup:

```bash
docker compose up -d postgres
```

Verify it is healthy:

```bash
docker compose ps
```

Copy the environment template:

```bash
cp .env.example .env
```

Then set your existing API credentials in `.env`. The persistence settings are:

```env
DATABASE_URL=postgresql://arthavani:arthavani@localhost:5432/arthavani
CONVERSATION_THREAD_ID=default-user
```

`CONVERSATION_THREAD_ID` identifies the conversation to resume. For this single-user project, `default-user` is a useful development default. Later, replace it with a real authenticated user/session identifier.

### Run ArthaVani

```bash
source .venv/bin/activate
python main.py
```

### Tests

Run the normal test suite with:

```bash
pytest -q
```

The PostgreSQL restart-persistence test is skipped unless `DATABASE_URL` is configured. To exercise it locally, start Postgres and run:

```bash
DATABASE_URL=postgresql://arthavani:arthavani@localhost:5432/arthavani pytest -q tests/test_postgres_persistence.py
```

## Repository structure

```text
finance_agent/
  graph.py            # LangGraph state graph
  runner.py           # async runner + Postgres checkpointing
  tools.py            # LLM-facing native tools
  providers/          # Groww, Yahoo, AMFI, FX, NSE, watchlist providers

voice/
  audio/              # microphone, speaker, resampling, AEC
  llm/                # conversation-to-agent bridge
  stt/                # Deepgram streaming STT
  text/               # streaming sentence splitting
  tts/                # Edge TTS
  vad/                # Silero speech detection
```
