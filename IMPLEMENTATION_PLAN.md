# SCUT implementation plan

## Architecture

1. A standard-library Python backend exposes a localhost/LAN Control Center, REST API, and authenticated WebSocket protocol.
2. Machine-specific paths, credentials, bootstrap state, and device credentials live only in `.local`.
3. A Windows audio adapter records only an explicitly requested diagnostic and reports unsupported capture strategies honestly.
4. Faster-Whisper is an optional locked runtime dependency: CPU is the baseline and GPU is enabled only after a real inference self-test.
5. A Java Android thin client uses the documented protocol; the prebuilt APK is copied to `dist` for runtime.

## Vertical slices

- [x] Portable layout, contracts, machine-state boundary — verify path/unit tests.
- [x] Classifier and state machine — verify deterministic tests.
- [x] Backend status/pairing/WebSocket/alerts — verify integration tests.
- [x] Control Center — verify in an actual browser.
- [x] Android client — build and inspect APK.
- [x] Bootstrap, start, package and portability scans — run scripts/tests.

## Risks

| Risk | Mitigation |
|---|---|
| Phone Link may expose no call-audio endpoint | Test process, endpoint and safe-routing strategies; persist a blocker report, never fake a pass. |
| GPU differs by laptop | CPU baseline; model device only becomes GPU after an inference self-test. |
| Venue internet is unreliable | Cache-first bootstrap with hash checks and repeatable downloads. |
