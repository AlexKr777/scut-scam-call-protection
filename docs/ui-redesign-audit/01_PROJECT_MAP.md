# SCUT project map

## Shape

One primary Python HTTP service with embedded static web UI, Windows-native audio helpers, and a separate Android companion. This is not Electron, Tauri, or a monorepo with a desktop wrapper.

```text
backend/                 Python service, capture orchestration, STT/risk engines
frontend/                Static Control Center (index.html, app.js, styles.css)
windows-audio/           C++ Windows Core Audio helpers and built .exe artifacts
android/app/src/main/    Java Android pairing/alert client
scripts/                 bootstrap, startup, configuration and evaluation scripts
tests/                   Python unit/replay tests
.local/                  runtime-generated machine config and paired devices (excluded)
diagnostics/, logs/      runtime-generated diagnostics/logs (excluded)
bootstrap-cache/, dist/, output/, reports/  dependencies, builds/models/evaluation output (excluded)
```

## Runtime-relevant ownership

| Area | Technology | Responsibility | Status |
|---|---|---|---|
| Control Center | Python `http.server` + vanilla HTML/CSS/JS | serves UI, REST and hand-written WebSocket | VERIFIED |
| Core | Python | modes, transcript/risk state, pairing, diagnostics | VERIFIED |
| Caller capture diagnostic | C++/Windows Core Audio | process loopback WAV test against discovered Phone Link process | VERIFIED, explicit-only |
| Ongoing test transcription | C++ + Python | guarded communications system mix and optional communications mic | VERIFIED, TEST only and not process-attributed |
| STT | `faster-whisper`, local model | final utterance transcription | VERIFIED when models/runtime available |
| Risk | local semantic/rule engines, optional OpenAI-compatible provider, optional local Nomic artifact | classify finalized transcript text | VERIFIED with availability caveats |
| Android | Java / native Android APIs | authenticated WebSocket alert notification/vibration/overlay | VERIFIED |

Dependencies are pinned in `requirements.lock`; the launcher starts `backend/server.py`, and the web UI is files served by that process (`START_SCUT.bat:3-4`, `scripts/start-scut.ps1:1-10`).

## Exclusions

Deep source analysis excluded dependency environments, Android build outputs, executable/object artifacts, models, reports, raw diagnostics, logs, `dist`, and training output. Source/configuration explaining them was inspected.
