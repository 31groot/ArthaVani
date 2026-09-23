# ArthaVani Web UI

This package adds the single-page React experience for the current FastAPI
backend.

## User flow

```text
/auth
  ↓
register / login
  ↓
/connect
  ↓
one-time Groww connection
  ↓
/
single-page dashboard
```

The dashboard contains:

- portfolio value / P&L / holding count
- current portfolio holdings
- market headlines
- portfolio-relevant "Hot news"
- NSE market status
- ArthaVani assistant chat
- browser microphone input where Web Speech API is available
- browser speech output for assistant replies

## Important voice note

The microphone button in this first web UI uses the browser's native
SpeechRecognition API to turn speech into text, then calls the existing
`POST /api/v1/chat` endpoint. Replies are spoken with the browser's
SpeechSynthesis API.

This is intentionally a lightweight web bridge. It does not yet stream the
existing local Deepgram/VAD/Edge-TTS pipeline to the browser. A native browser
voice transport can be added as the next step with a FastAPI WebSocket.

## Backend dashboard endpoint

The UI expects:

`GET /api/v1/dashboard`

The endpoint aggregates the authenticated user's portfolio, market news,
portfolio-relevant headlines, and market status.

Apply `backend_patch/main_dashboard_import_and_route.txt` to your FastAPI
backend and copy `backend_patch/api/dashboard.py` to `api/dashboard.py`.

## Run

### Backend

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

`http://127.0.0.1:5173`

Vite proxies `/api/*` to `http://127.0.0.1:8000` during development.

## Production

Build:

```bash
npm run build
```

Serve the `dist/` directory from your preferred static host or reverse proxy.
Keep the FastAPI backend behind HTTPS and configure `VITE_API_BASE_URL` for the
deployed API origin.

## Packages

This UI targets the current React 19.3, Vite 8.3, and React Router 7.18 line.


## v2 UI changes

- Reworked dashboard and onboarding into a calm light financial-terminal style.
- Inter is used for UI copy; IBM Plex Mono is used for financial figures.
- Removed gradients, glass effects, glowing cards, and oversized visual blocks.
- The assistant now exposes a clear microphone action with "Tap Speak to talk".
- Browser voice uses `SpeechRecognition` / `webkitSpeechRecognition`, starts
  from the mic button, captures the spoken question, and automatically sends
  it when speech ends.
- Browser speech synthesis still reads ArthaVani's answer aloud.
- If microphone permission is blocked, the assistant shows the exact reason.
- Added `lucide-react` to the frontend package dependencies.


### Persistent sign-in + Groww connection

On login, the UI now fetches both the authenticated user and the existing
Groww connection status before deciding where to route the user. A user with
an existing Groww connection goes directly to the dashboard; only a user
without a connection is sent to the Groww onboarding screen.

Groww credentials remain server-side. They are not stored in localStorage or
returned to the browser. The backend persists the encrypted Groww connection
against the authenticated user ID in PostgreSQL.
