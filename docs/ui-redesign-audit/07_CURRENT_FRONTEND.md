# Current frontend functional inventory

The current frontend is a single vanilla static screen, no router, framework, state store, local storage, component system, charts, or desktop bridge. `server.py` serves it from `frontend/` (`backend/server.py:33-38`).

| Screen/section | Data/actions | Real vs missing |
|---|---|---|
| Control Center header + protection state | WebSocket connection marker, latest risk, OFF/TEST/PROTECT | REAL latest state; no historical/rich risk display |
| Machine/audio/intelligence/Android cards | status fields | REAL probes/configuration; not proof capture is live |
| Live caller context | latest status transcript; manual diagnostic text submission | REAL endpoint; label explicitly says injected diagnostic |
| Latency | three in-memory metrics | REAL when events occurred; not persisted |
| Diagnostic/pair actions | all documented POST routes | REAL; results largely only toast/fields |
| Capture result + recording playback | audio status attempt list and recording endpoint | REAL explicit diagnostic only |
| Runtime events / pairing payload | latest 20 events, generated payload | REAL; pairing token must be treated as secret |

Current live WebSocket handler rerenders statuses and displays `alert` as a browser toast; it ignores `risk_event`, `decision`, and `FINAL_TRANSCRIPT` payload details (`frontend/app.js:8-14`). The UI polls status every five seconds in addition to WebSocket updates (`frontend/app.js:9,14`).

## Do not accidentally lose in replacement

Mode control; explicit transcript injection; Android pairing workflow; all five diagnostics; verified-recording playback; capture candidate telemetry; status probes; WebSocket reconnect; alert toast; latest in-memory event/latency visibility. HTML source inventory: `frontend/index.html:10-36`.
