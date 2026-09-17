# AI and alert logic

## Ingestion and decision — VERIFIED

Every accepted stable transcript is added to an in-memory 12-item deque, sent to `SemanticRiskEngine`, then to `HybridBrainV1`; `PROTECT` sends an alert only if the hybrid result is `CRITICAL` (`backend/services.py:309-341`). HTTP transcript injection is explicit software diagnostic input; live ASR passes `explicit=False`.

Local semantic analysis recognizes caller-directed credential, money, remote-access, link, approval, loan, cash and pressure facts while suppressing protective, quoted, hypothetical, and discussion contexts (`backend/hybrid_v1.py:55-151`; `backend/semantic_risk.py:197-231`). Hybrid returns `risk_level`, numeric `risk_score`, `alert_recommended`, reason code, requested actions, evidence with normalized/original spans, protective context, languages, conversation state and trace (`backend/hybrid_v1.py:160-189`).

## Optional provider — PARTIAL

Only in `PROTECT`, `provider_from_environment` creates an OpenAI-compatible provider when required environment variables are valid. It sends bounded recent finalized turns (up to eight) and accumulated identity/scenario/action state, asks for constrained facts, validates enums, then applies deterministic policy. It retries malformed structured output once; provider errors yield `DEGRADED` and retain the local fast path. The provider never supplies a direct risk label (`backend/services.py:145-153`; `backend/semantic_risk.py:90-153`, `182-273`).

`NomicDeploymentV1` is lazy and optional; its failure is caught and reported as unavailable. Its loader depends on a CUDA model artifact and a machine-specific cache location, so deployment availability cannot be inferred from source (`backend/services.py:343-354`, `backend/nomic_deployment_v1.py:9-23`).

## Alert flows

| Flow | Trigger / payload | Persistence / cancel / suppression | UI reality |
|---|---|---|---|
| Automatic | `PROTECT` plus hybrid `CRITICAL`; sends warning built from risk + current text | no alert entity, no dismissal/cancel endpoint, no cooldown or dedupe; every qualifying accepted transcript can send a new alert | browser sees only toast; Android receives full alert event |
| Explicit test | `POST /api/alerts/test`; synthetic critical decision | no persistence | browser button calls it |
| Manual “something feels wrong” | NOT IMPLEMENTED | N/A | no control or backend command |
| Android external | paired/authenticated session gets WebSocket `alert`; client vibrates, notifies, optionally overlays for 12 seconds, then ACKs | ACK only records a latency/event; it does not dismiss/cancel/alter risk | Android-only (`android/.../ScutService.java:17-27`) |

The alert event exposes `id`, `risk`, safe generic message, `source`, and `sentMonotonic`; `send_alert` returns only id/delivered client count (`backend/services.py:361-371`). Exact evidence, severity, reason codes and risk-event data exist in the separate `decision`/`risk_event` messages, but current browser ignores them (`frontend/app.js:14`).

## Reset and retrigger

Mode changes replace semantic and hybrid state and clear Nomic turns (`backend/services.py:145-156`). Within a mode, conversation evidence is bounded/expiry-aware (pressure eight turns; actions 32 turns) but alerts have no emitted-alert guard (`backend/hybrid_v1.py:36-53`, `backend/services.py:337-340`).
