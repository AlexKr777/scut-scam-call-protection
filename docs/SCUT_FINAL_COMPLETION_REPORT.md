# SCUT — final completion report

Date: 2026-09-08

Status: all authorised redesign gates are implemented; distribution artifacts were built and smoke-tested.

## Completed phases and gates

| Phase / gate | Completed work |
| --- | --- |
| Phase 0–1 | Read the authoritative brief, repository instructions, and audit material; preserved the existing Python service as product authority. |
| Gate A | Windows Electron shell, reusable warm SCUT design system, approved idle state, custom title chrome, sidebar, and DPI review. |
| Gate B | Typed WebSocket boundary, live final transcript document, real decision/evidence treatment, and contextual inspector. |
| Gate C | Separate always-on-top Electron Floating Bar with real backend-derived state, allowed IPC, monitor-safe placement, and capture review. |
| Gate D | Desktop Devices, Settings/Diagnostics, and capability-gated History and Alerts surfaces. |
| Gate E | Android companion activity and safety-overlay presentation; pairing/authentication/heartbeat/alert/ack service logic remains intact. |
| Gate F | Reproducible Windows NSIS installer, packaged backend/frontend runtime assets, installation guidance, APK build. |
| Gate G | Final desktop DPI review, production-package and installed-app smoke tests, test/build checks, and this report. |

## What was implemented

### Desktop product

- The Electron bridge remains narrow and allow-listed. New controls call only existing backend endpoints for protection mode, pairing, explicit diagnostics, explicit Android test alerts, stable diagnostic transcript input, and an existing diagnostic recording URL.
- **Devices** presents the actual connected/offline Android state, device metadata, and permission heartbeat fields when supplied by the backend. Pairing returns the genuine backend payload; it does not invent a device, QR pairing, or acknowledgement.
- **Settings** exposes existing explicit diagnostic operations and actual protection modes. Test controls label their outputs as explicit test activity; they do not claim alert delivery or capture success.
- **History** and **Alerts** intentionally show capability-gated empty states: the present backend has no persisted transcript/alert archive. No invented rows, scores, metrics, or event history were added.
- The Android view is a light SCUT companion surface. It continues to state that Android receives paired-PC alerts and does not capture cellular-call audio. The alert overlay was restyled only; its foreground-service, notification, vibration, pairing, authentication, heartbeat, acknowledgement, and 12-second removal behavior were preserved.

### Distribution

- `npm run package:win` builds `desktop/release/SCUT Setup 0.1.0.exe` using electron-builder/NSIS.
- `extraResources` packages the authoritative `backend` and legacy `frontend` into `resources/scut-runtime`, and packaged Electron resolves that location rather than a development-relative path.
- `BUILD_ANDROID.bat` builds `dist/SCUT.apk` from the real Android application.
- [INSTALL_WINDOWS.md](./INSTALL_WINDOWS.md) documents the actual Python/model requirements and fail-closed behaviour.

## Verification

| Check | Result |
| --- | --- |
| Desktop component/unit suite | **35 passed / 10 files** (`npm test`) |
| Type checks + production renderer/Electron build | **Passed** (as part of `npm run package:win`) |
| Windows NSIS package | **Built**: `desktop/release/SCUT Setup 0.1.0.exe` (118,261,403 bytes) |
| Installer SHA-256 | `C86EE0B0D3DABED8AD558CF2EF0FB1E2BE72B86E074978123CADCEE6EE617D47` |
| Unpacked production app | **Captured successfully** with the real backend started through `SCUT_PYTHON_PATH` |
| Installed-app smoke test | **Passed**: silent NSIS install to `desktop/release/installer-smoke`, then installed `SCUT.exe` produced a capture and retained both runtime assets |
| Android debug APK | **Built successfully** at `dist/SCUT.apk` |
| Production dependencies audit | **0 vulnerabilities** for `npm audit --omit=dev` |
| Neural-NLI regression subset | **6 passed** after restoring missing `onnxruntime` in the dedicated local GPU test runtime |

The broad backend discovery run in the small portable venv executed 166 tests, of which 153 passed; its 13 import errors were environmental (`numpy`, `torch`, `sklearn`) rather than product failures. The GPU test environment supplied those dependencies but lacked `onnxruntime`; after installation, the six affected neural tests pass. The heavyweight full GPU discovery suite spawns a child process which outlives this terminal capture wrapper, so an exit summary could not be captured here; no failure was observed after the child completed. This is an environment-verification limitation, not a change to backend behaviour.

Android Gradle completed with upstream toolchain warnings (AGP 8.8.2 is tested through compileSdk 35 while this project uses 36; Java 21 warns about source/target 8). The APK build itself succeeded.

## Final visual/runtime artifacts

| Review | Artifact |
| --- | --- |
| Packaged desktop, 1360 × 860 | [SCUT_FINAL_PACKAGED_HOME_1360x860.png](./final/SCUT_FINAL_PACKAGED_HOME_1360x860.png) |
| Installed desktop, 1360 × 860 | [SCUT_FINAL_INSTALLED_HOME_1360x860.png](./final/SCUT_FINAL_INSTALLED_HOME_1360x860.png) |
| Home at 125% scaling, 1920 × 1080 output | [SCUT_FINAL_HOME_1920x1080_125pct.png](./final/SCUT_FINAL_HOME_1920x1080_125pct.png) |
| Home at 150% scaling, 1920 × 1080 output | [SCUT_FINAL_HOME_1920x1080_150pct.png](./final/SCUT_FINAL_HOME_1920x1080_150pct.png) |
| Gate B live document and inspector | [Gate B report](./gate-b/SCUT_GATE_B_REPORT.md) |
| Gate C Floating Bar | [Gate C report](./gate-c/SCUT_GATE_C_REPORT.md) |

Review conclusion: the approved cream/ink/green baseline survives package launch at 100%, 125%, and 150% without clipping or text overflow. The idle state remains quiet and truthful; no dashboard cards or invented operational data appear.

## Deviations and known limitations

- The installer is **unsigned** because no code-signing certificate was provided. `signAndEditExecutable` is disabled to make the local unsigned build reproducible under this Windows policy; SmartScreen reputation warnings are therefore possible.
- Electron-builder used its fallback icon because the repository has no Windows `.ico` asset. This does not alter runtime behaviour, but a branded signed release should supply one before public distribution.
- The installer includes source/runtime assets but deliberately does not include a large Python environment, model cache, secrets, recordings, or user-specific device state. Supply a compatible Python runtime through `SCUT_PYTHON_PATH` (or Windows `py -3.12`) as described in the install guide. If it is absent, the application fails closed instead of fabricating protection status.
- No physical Android device or multi-monitor desktop was attached to this workstation. APK compilation and protocol-preserving source review passed; physical pairing/overlay delivery and secondary-monitor placement remain hardware acceptance checks.
- Backend persistence does not exist in the supplied product. History/Alerts remain explicitly empty/capability-gated until a real persisted backend contract is added.

## Run and install

1. Install [SCUT Setup 0.1.0.exe](../desktop/release/SCUT%20Setup%200.1.0.exe) and launch **SCUT** from the Start menu or desktop shortcut.
2. Before launch, expose a compatible backend runtime. For a repository checkout, run `FIRST_RUN.bat`, `CONFIGURE.bat`, and `START_SCUT.bat`; for the installer, set `SCUT_PYTHON_PATH` to the compatible `python.exe` described in [INSTALL_WINDOWS.md](./INSTALL_WINDOWS.md).
3. Install [SCUT.apk](../dist/SCUT.apk) on Android 8.0+, grant the requested notification/overlay permissions, then create the genuine pairing payload from **Devices** on the Windows app.
4. Use **Settings** only for explicit diagnostics. Keep protection OFF until real capture diagnostics support the requested mode.

## Relevant commits

- `7e29177` — truthful Floating Bar state mapper
- `bf888f9` — separate always-on-top Floating Bar
- `d865328` — truthful Devices, Settings, History, and Alerts capability surfaces
- `0aa22fe` — Android companion/overlay visual refresh
- `3dd7a09` — Windows NSIS packaging and runtime assets

Earlier approved Gate A–B commits and their evidence remain recorded in the linked gate reports.
