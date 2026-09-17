# SCUT Gate A - shell and design-system calibration

Date: 2026-09-08

Status: implemented and reviewed; visual direction is not yet approved

## Scope boundary

This delivery completes Phase 0, Phase 1, and Gate A only. It does not implement Live Transcript, the inspector, Floating Bar, Android redesign work, History, Alerts, later Devices/Settings flows, packaging, or distribution. Only the exact phrase `GATE A APPROVED` authorizes Gate B.

## Phase 0 - verified product truth

The full `SCUT_Design_Spec_and_Codex_Master_Brief.docx` was read before implementation. The repository brief, README, existing browser UI, backend entrypoint/configuration, status and lifecycle services, diagnostics/transcript services, launcher, tests, and every audit referenced by the brief (`00`, `03`-`10`) were inspected.

Verified baseline:

- The existing product was a Python backend plus browser UI, not a Windows desktop shell.
- The backend contract is usable through `/health`, `/api/status`, and `/ws`.
- The status model exposes `OFF`, `TEST`, and `PROTECT`, but a selected mode does not prove continuous Phone Link capture.
- The real machine snapshot used by the idle composition is `OFF`, audio `IDLE / NOT TESTED`, Android `OFFLINE`, with no real recent events.
- The existing backend suite passed in the configured local Python environment.
- The checked-in `.local/venv` is not portable on this machine. The desktop launcher probes valid interpreters and falls back to the installed Python 3.12 runtime.

## Phase 1 - desktop foundation

The Windows surface lives in `desktop/` and uses Electron, React, TypeScript, and Vite. Existing Python business logic and the browser frontend are preserved.

Implemented foundation:

- A real Electron `BrowserWindow` with 1360 x 860 default outer bounds and 1080 x 720 minimum bounds.
- Windows title-bar overlay with a 44 px draggable chrome region and native window controls.
- Context isolation, renderer sandboxing, Node integration disabled, permission denial by default, new-window denial, and cross-origin navigation blocking.
- A narrow preload bridge exposing only health, status, and capture-readiness messages.
- Desktop-managed Python backend lifecycle with external-instance reuse, health probing, stale-venv skipping, bounded startup, and owned-process shutdown.
- Typed backend contracts and presentation-state derivation so copy remains honest about mode, capture verification, Android connectivity, and real activity.

## Gate A - final visual direction candidate

The revised shell uses the brief's Granola x Wispr Flow reference system without copying either product:

- Warm paper layers, a deeper beige navigation rail, exact stone dividers, ink typography, disciplined SCUT green, and amber only for an unverified capture path.
- Instrument Sans for interface text and Bitter at medium weight for the editorial state headline.
- A compact 188 px navigation rail, custom bracket/signal mark, restrained line icons, and a quiet selected state.
- One large living protection object instead of a dashboard card grid.
- An asymmetric `Current setup` rail that separates primary state from factual readiness details.
- Short layered entrance settles, tactile hover/focus feedback, and a reduced-motion override.
- All visible operational states come from real `/health` and `/api/status` responses. No call, count, transcript, score, alert, or capture capability is fabricated.

## Visual self-review against the embedded references

The initial Gate A screenshots were below the brief's bar: the page read as a correct but generic wireframe, with a large heading followed by three interchangeable dashboard rows. The second calibration pass rebuilt the composition rather than extending that direction.

What now aligns with Granola:

- A calm warm field, narrow dense navigation, fine dividers, editorial type contrast, and notebook-like rather than SaaS-like materiality.
- Information is placed on one continuous paper surface instead of inside a collection of rounded cards.
- Negative space creates a deliberate reading order: live state, meaning, then setup detail.

What now aligns with Wispr Flow:

- The protection state is expressed as one recognizable object with an oversized editorial statement.
- System presence is persistent but quiet, with a single bright status accent and restrained motion.
- The voice-purple accent is intentionally absent while idle; the brief assigns it to later listening/transcription states.

Defects identified and corrected in the live renderer:

1. Replaced the generic equal-weight readiness ledger with a dominant state lockup and a narrower semantic setup rail.
2. Reduced the unfinished-wireframe feeling by introducing paper depth, a custom state glyph, stronger type contrast, and a more deliberate vertical rhythm.
3. Removed ambiguous empty-state language and exposed actual `OFF`, unverified capture, offline companion, and no-activity facts.
4. Improved state-glyph contrast and material separation after the first revised capture.
5. Increased the privacy footnote size and corrected the canonical stone token to `#DED7C8`.
6. Preserved proportions and text flow at both required Windows scale configurations without clipping or scrollbars.

Deliberate constraints:

- Later navigation destinations remain visible but disabled; activating them would imply Gate B or later work.
- The idle page stays sparse because the backend reports no real recent call or event. Decorative fake data was not added to imitate reference density.
- Purple voice visualization, transcript surfaces, and floating controls remain out of scope.

## Review captures

| Artifact | Renderer viewport | Scale | Output pixels |
|---|---:|---:|---:|
| [SCUT_GATE_A_1440x900.png](./SCUT_GATE_A_1440x900.png) | 1440 x 900 DIP | 100% | 1440 x 900 |
| [SCUT_GATE_A_1920x1080_125pct.png](./SCUT_GATE_A_1920x1080_125pct.png) | 1536 x 864 DIP | 125% | 1920 x 1080 |

Both captures were produced by the built Electron renderer after a real backend response, bundled fonts, and entrance motion had settled. The normal Electron application was also launched from the production build and left running for review.

## Verification

- Desktop unit/component/integration tests: 16 passed across 5 files.
- TypeScript checks: passed for renderer and Electron processes.
- Production renderer/Electron build: passed.
- Python backend regression suite: 198 passed in the Phase 1 verification run.
- Runtime health: `/health` returned protocol version 1 and the shell displayed `Connected - Protocol v1`.
- Required captures: exact dimensions confirmed and visually inspected.

Gate A stops here and awaits explicit visual-direction approval.
