# SCUT Gate C — Floating Bar

Date: 2026-09-08

Status: implemented and verified

## Scope

This delivery implements Gate C only: SCUT's dedicated always-on-top Windows Floating Bar. It does not implement Devices, Diagnostics UI, History, Alerts, Settings, Android redesign, packaging, or any later gate.

## Real desktop surface

- Electron now owns a separate frameless, transparent `SCUT Voice Bar` `BrowserWindow`. It is always on top, visible across workspaces, excluded from the taskbar, movable, and initially placed inside the work area of the display containing the main window.
- The bar starts as a 196 × 48 px neutral resting surface. A real audio-listening, analysis, capture-error, reconnect, or non-safe backend decision maps it to one of the bounded designed states; the only expanded size is 332 × 58 px.
- The Electron main process animates window bounds for 220 ms when the presentation changes. The renderer crossfades surface feedback without a hard redraw. The waveform is present and animated only while an actual `STARTING` or `CAPTURING` state is reported by the backend.
- The `Open SCUT` control appears only on a real non-safe risk decision. It restores and focuses the main window. There is no manual-alert control, hidden or otherwise, because the backend exposes no such capability.

## Truthful state mapping

| Bar state | Only shown when the service reports |
|---|---|
| Resting | live connection with no active audio/error/risk state |
| Listening | `audio.state` is `STARTING` or `CAPTURING` |
| Analysing | `FINAL_TRANSCRIPT`, `FAST_PARTIAL`, or `STABLE_TRANSCRIPT` |
| Risk | backend `risk.level` is `WATCH`, `SUSPICIOUS`, `HIGH_RISK`, or `CRITICAL` |
| Error | an observed backend audio error/failure state |
| Reconnecting | WebSocket connect/reconnect failure |

Incoming WebSocket frames remain normalized through the existing typed Gate B boundary. The bar does not fabricate transcript text, duration, score, detection state, alert delivery, or capture state. Its small listening elapsed label begins only after a real listening state arrives; it is not a call duration.

## Runtime review

The production Electron build was launched with both the main window and the independent `SCUT Voice Bar` window. The local service was verified healthy at protocol v1.

1. With actual `OFF / IDLE / SAFE` status, the bar stayed 196 × 48, displayed `Local service`, and rendered no waveform.
2. The service was set to `TEST` and the existing supported diagnostic transcript route accepted a stable scam phrase. The backend emitted actual `CRITICAL / OTP_REQUESTED` data through its normal WebSocket pathway.
3. The bar morphed to 332 × 58 and rendered only `Critical signal` and `OTP_REQUESTED`, plus its `Open SCUT` affordance. It did not claim an Android alert delivery or show invented score/evidence/transcript content.
4. The service was returned to `OFF / IDLE / SAFE` after the capture.

The geometry unit test covers both a primary work area and a separate positive-coordinate secondary work area. This workstation did not expose a physical second display during review, so that portion is deterministic geometry coverage rather than a physical multi-monitor observation.

## Review captures

| State | Artifact | Isolated Electron content size |
|---|---|---:|
| Resting, actual `OFF / IDLE / SAFE` | [SCUT_GATE_C_BAR_REST_196x48.png](./SCUT_GATE_C_BAR_REST_196x48.png) | 196 × 48 |
| Risk, actual `CRITICAL / OTP_REQUESTED` | [SCUT_GATE_C_BAR_RISK_332x58.png](./SCUT_GATE_C_BAR_RISK_332x58.png) | 332 × 58 |

Visual self-review: the resting bar is intentionally almost neutral and low-noise. Lilac is reserved for actual voice states; rust is restricted to `CRITICAL`. The risk bar changes temperature once but avoids persistent pulse, a red takeover, generic card chrome, or a fake alert/delivery claim. The small footprint and work-area inset make it an OS-level tool rather than a competing app window.

## Verification

- Full desktop suite: 32 tests across 9 files passed.
- Production renderer/Electron build: passed.
- Focus/click behavior: component integration test invokes `Open SCUT`; the narrow IPC handler calls `show()` and `focus()` on the main `BrowserWindow`.
- Size IPC boundary: tested to accept only 196 × 48 and 332 × 58 requests, and rejects other geometry.
- Multi-monitor placement: deterministic primary and secondary work-area geometry tests passed.
- Runtime backend final state: health `ok`, protocol v1, `OFF / IDLE / SAFE`.

## Reproducible capture commands

From `desktop/`, after `npm run build`:

```powershell
node scripts/electron-launch.mjs --capture-output=../docs/gate-c/SCUT_GATE_C_BAR_REST_196x48.png --capture-surface=floating --capture-width=196 --capture-height=48 --capture-delay-ms=750
```

The risk capture additionally requires the already-running local service in `TEST` mode and uses its pre-existing diagnostic input endpoint:

```powershell
node scripts/electron-launch.mjs --capture-output=../docs/gate-c/SCUT_GATE_C_BAR_RISK_332x58.png --capture-surface=floating --capture-width=332 --capture-height=58 --capture-transcript="Move the payment to the protected account now and give me the six digit SMS code." --capture-delay-ms=1500
```
