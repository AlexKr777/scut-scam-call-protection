# SCUT Gate A architecture and visual calibration

Date: 2026-09-08

## Authority and scope

This note implements only Phase 0, Phase 1, and Gate A from `SCUT_Design_Spec_and_Codex_Master_Brief.docx`. The external brief, `PROJECT_BRIEF.md`, `README.md`, and `docs/ui-redesign-audit/*` remain authoritative. Existing Python risk, audio, Phone Link, transcription, pairing, and alert logic is untouched.

Gate A includes a real Electron Windows shell, backend lifecycle/health connection, custom product chrome, design tokens, typography, narrow navigation, and the first truthful Home/idle composition. Live Transcript, the floating voice bar, Android redesign, functional History/Alerts/Devices/Settings pages, diagnostics migration, and packaging are explicitly out of scope.

## Phase 0 evidence

- Baseline checkpoint: Git repository initialized; existing MVP committed on `main` at `f27b2f4`; Gate A work uses `feature/gate-a-desktop-shell`.
- Backend tests: 198 tests passed under installed Python 3.12 in 23.666 seconds.
- Backend health: `/health` returned `{ok: true, protocolVersion: 1}` and `/api/status` returned the real idle state: `OFF`, audio `IDLE`, Android `OFFLINE`, risk `SAFE`, zero events.
- Portability caveat: `.local/venv/pyvenv.cfg` still points to the prior machine. The desktop lifecycle must verify Python candidates instead of assuming this copied venv is runnable.
- Existing browser Control Center remains unchanged as the fallback.

## Architecture decision

Use Electron 44 + React 19 + TypeScript 7 + Vite 8 in a new `desktop/` subtree.

- Electron main process owns the main `BrowserWindow`, starts the existing Python server only when `/health` is unavailable, waits on health rather than sleeping, records whether it owns the process, and stops only an owned child on quit.
- Python resolution checks a configured `SCUT_PYTHON_PATH`, the project-local venv, `py -3.12`, and `python` in order. A failed/stale candidate is skipped; backend business code is never modified.
- The renderer is sandboxed with Node integration disabled and context isolation enabled. A narrow preload bridge exposes only typed health/status calls; arbitrary IPC is not exposed.
- The renderer normalizes the current partial/mutable status shape into a stable Home view model. It never derives capabilities from fixture data.
- Development loads Vite from localhost; production loads bundled renderer files. The legacy `frontend/` stays served by Python.
- Packaging model for this phase: unpackaged development Electron application with a real top-level Windows window. Installer work belongs to Phase 10 and is not started.

## Visual thesis

SCUT is a quiet warm-paper Windows notebook with an alert mind underneath: calm at rest, precise about uncertainty, and visually native without looking like an admin dashboard.

- Base environment: calibrated cream paper, stone divider, green-black ink, muted beige metadata, and one calm SCUT green state accent.
- Type: Instrument Sans for UI and body; Bitter only for the large idle phrase. Weight and spacing create hierarchy before size.
- Geometry: 44 px product title bar; 188 px sidebar; open content canvas; 8/12/18 px radii only where structure requires them; no card grid.
- Home content: truthful mode/readiness statement, Phone Link verification line, Android connection line, and one last real event or “No recent activity.” No calls, metrics, charts, or synthetic history.
- Brand mark: an original protection bracket intersected by a tiny signal line; no shield/checkmark.

## Interaction thesis

- Initial content materializes with a 520 ms, 6 px rise using the brief's reveal easing.
- Navigation indicator and background tint transition in 160 ms; non-Home items remain visibly present for shell calibration but are honestly marked unavailable in this gate.
- Connection/status dots use a single arrival transition and static settled state. Nothing pulses or loops.
- `prefers-reduced-motion` removes travel and collapses durations to short fades.

## Exact implementation boundary

Create or modify only:

- `.gitignore` — exclude desktop dependencies, generated build output, and Gate A capture artifacts.
- `desktop/package.json`, lockfile, TypeScript/Vite/Vitest configuration — isolated desktop toolchain.
- `desktop/electron/backend-process.ts` — backend discovery, start, health wait, owned shutdown.
- `desktop/electron/main.ts` — secure main window and IPC handlers.
- `desktop/electron/preload.ts` — minimal typed bridge.
- `desktop/src/api/*` — backend contracts and normalization.
- `desktop/src/components/*` and `desktop/src/App.tsx` — brand, shell, sidebar, idle Home.
- `desktop/src/styles/*` — local fonts, tokens, layout, motion, responsive/DPI behavior.
- `desktop/tests/*` — view-model and lifecycle behavior tests.
- `desktop/scripts/capture-gate-a.mjs` — exact-resolution Electron capture harness.
- `docs/gate-a/` — final screenshot review artifacts only.

No backend, legacy frontend, Android, diagnostic, risk, transcript, or alert source is changed.
