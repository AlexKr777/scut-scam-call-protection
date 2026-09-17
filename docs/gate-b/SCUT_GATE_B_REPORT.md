# SCUT Gate B - live transcript and contextual inspector

Date: 2026-09-08

Status: implemented and verified

## Scope

This delivery implements Gate B only: the desktop live transcript workspace, final-text reveal, evidence treatment, and contextual risk inspector. It does not implement the Floating Bar, Android UI, History, Alerts, Devices, Settings, packaging, or any later gate.

## Real-time integration

- The renderer obtains a single runtime WebSocket endpoint through the existing narrow Electron bridge. It does not hard-code a local port.
- A typed boundary validates every socket payload before it reaches React state. Supported messages are `hello`, `status`, `FINAL_TRANSCRIPT`, `risk_event`, `decision`, and `alert`; malformed payloads are ignored.
- `decision` and `FINAL_TRANSCRIPT` may arrive in different order. The reducer merges them into one finalized transcript line rather than duplicating content.
- The current backend `status.transcript` is used only when it arrives inside a real decision event. No fabricated transcript, timestamp, speaker, risk score, or evidence is introduced.
- Returning to a real backend `OFF` status clears the temporary live session and restores the truthful Gate A idle surface.
- An Android confirmation is rendered only after a real `alert` WebSocket event, and states that the event was emitted without claiming delivery or acknowledgement.

## Interaction and visual direction

- Home switches from the approved idle composition to a transcript-first open paper document when a real finalized/decision-backed line exists.
- The top metadata line stays quiet: local stream state and actual protection mode only.
- Final text uses the required materialization motion (clip/reveal, 6 px rise, 540 ms). Evidence arrives shortly afterwards as a restrained amber/rust marker, never a red page takeover.
- The document uses a narrow final-state/timestamp column, speaker label, sans-serif reading body, and a maximum readable measure near the brief's 62-78 character guidance.
- `Why this stood out` is a native button. It opens a 320 px contextual inspector on demand; closing it returns the document to its full width.
- The inspector uses only real decision/risk-event fields: reason, level, actual score, requested actions, and evidence spans. Long evidence scrolls inside the inspector, not across the entire application workspace.

## Real runtime review

The final review used the production Electron window and the backend's supported safe diagnostic transcript input in `TEST` mode:

- The backend accepted the input and emitted `CRITICAL` with `OTP_REQUESTED` through the real WebSocket pathway.
- The renderer displayed the final text, soft evidence marker, critical label, and inspector content from the emitted decision.
- The app was then returned to backend `OFF`; the live workspace cleared and the approved idle state reappeared.

The capture-only `--capture-transcript` option exists solely in the Electron screenshot harness. It posts to the pre-existing `/api/transcripts` diagnostic endpoint; no Python route, decision logic, or product-facing injection control was added.

## Visual review captures

| State | Artifact | Window size |
|---|---|---:|
| Transcript, inspector closed | [SCUT_GATE_B_LIVE_1360x860.png](./SCUT_GATE_B_LIVE_1360x860.png) | 1360 x 860 |
| Transcript, inspector open | [SCUT_GATE_B_INSPECTOR_1360x860.png](./SCUT_GATE_B_INSPECTOR_1360x860.png) | 1360 x 860 |

The closed view confirms the transcript remains a document rather than a dashboard card. The open view confirms that evidence remains contextual, secondary, and scroll-contained.

## Verification

- Desktop tests: 22 passed across 6 files.
- Renderer and Electron TypeScript checks: passed.
- Production Electron/renderer build: passed.
- Real backend health: `ok`, protocol v1.
- Real safe-input review: accepted critical transcript, visualized through the production Electron WebSocket connection, then reset to `OFF`.
