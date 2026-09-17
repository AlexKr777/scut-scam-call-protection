# Frontend/backend contract

## HTTP

| Method/path | Request | Response/use | Current browser consumer |
|---|---|---|---|
| GET `/api/status` | — | mode, machine, Whisper, audio, Android, Tailscale, AI status, latest risk/transcript, metrics, last 20 events | rendered and polled every 5 s |
| GET `/health` | — | `{ok, protocolVersion}` | none |
| GET `/api/diagnostics/recording` | — | WAV only after selected capture | playback button |
| POST `/api/mode` | `{mode: OFF|TEST|PROTECT}` | refreshed status | mode buttons |
| POST `/api/pair` | `{}` | endpoint, one-time pairing token, expiry | pairing panel |
| POST `/api/transcripts` | `{text}`; non-empty <=4000 | accepted/risk/reason/riskEvent/hybrid/possibly alert | diagnostic input |
| POST `/api/alerts/test` | `{}` | synthetic alert result | button |
| POST `/api/diagnostics/{capture,earbuds,network,predemo,guarded-transcription}` | explicit test source required for capture | diagnostic-specific status | buttons |

Error envelope is `{error:{code,message}}`; body must be JSON object 1..65536 bytes. Route evidence: `backend/server.py:50-131`.

### `GET /api/status` key fields

| Field | Meaning | UI reliability |
|---|---|---|
| `mode` | OFF/TEST/PROTECT | YES |
| `machine`, `whisper`, `tailscale`, `android`, `anyModel` | current probes/configuration | YES, probe/config not a functional guarantee |
| `audio` | mutable latest capture/diagnostic state, strategy/source and sometimes candidate data | PARTIAL; shape varies by state |
| `risk` | latest decision level/reason/source | YES for latest only |
| `transcript` | latest plain text | YES for latest only |
| `metrics` / `events` | in-memory latest timings/events | PARTIAL; ephemeral |

Evidence: `backend/services.py:117-143`.

## WebSocket `/ws`

Server accepts pairing/auth/mobile messages and browser `subscribe` without auth. Messages server→client: `hello`, `status`, `risk_event`, `decision`, `FINAL_TRANSCRIPT`, `alert`, plus errors/pong. Android-only inbound messages are `pair`, `auth`, `heartbeat`, `ack`; pairing credentials should never be surfaced in redesign UI/logs (`backend/server.py:134-232`, `backend/services.py:275-307`, `309-371`).

## Exposed but unused by browser

- `risk_event` full semantic event (level, reasons, evidence IDs, scenario, severity, provider status).
- `decision` full hybrid evidence, score, requested actions and trace.
- `FINAL_TRANSCRIPT` speaker/audio start/end.
- `/health`; network/earbud/predemo diagnostics beyond a toast.

## Not available for a redesign without backend work

Call list/history, alert list/history, persisted transcript segments, dismiss/cancel/manual alert, configuration changes, real-time continuous Phone Link capture control, user settings CRUD, and a stable typed event/schema version beyond protocol v1.
