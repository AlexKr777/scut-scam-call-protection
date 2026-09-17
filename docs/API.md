# SCUT protocol v1

All REST errors use `{ "error": { "code": "UPPER_SNAKE", "message": "safe text" } }`. Responses are JSON UTF-8. The dashboard is same-origin; Android uses the WebSocket endpoint from its pairing payload.

| Endpoint | Use |
|---|---|
| `GET /api/status` | Sanitized live machine/application status |
| `POST /api/mode` | `{mode: OFF|TEST|PROTECT}` |
| `POST /api/pair` | Creates a short-lived one-time Android pairing token |
| `POST /api/transcripts` | Explicit stable transcript input/diagnostic |
| `POST /api/alerts/test` | Synthetic critical alert; never calls AnyModel |
| `POST /api/diagnostics/{name}` | Named safe diagnostic action |
| `GET /ws` | Dashboard or Android WebSocket protocol |

Android sends `pair`, then stores the returned credential. Reconnects send `auth`; then `heartbeat`, `ping`, and `ack`. Every critical alert has an id and delivery timestamps. Tokens expire in five minutes and credentials are randomly generated, never accepted from a query string.
