# SCUT portable MVP

SCUT protects a phone user during a normal cellular call. A Windows laptop captures the remote caller's digital audio where Phone Link permits it, locally transcribes multilingual speech, applies conservative local scam rules, optionally requests an AnyModel semantic decision, and pushes authenticated alerts to a paired Android client.

## Non-negotiable constraints

- The folder is copyable between Windows computers; all mutable machine state belongs in `.local`.
- `FIRST_RUN.bat` is idempotent and recreates project-local runtime state. `START_SCUT.bat` performs no heavy install.
- No secret, device ID, Computer-A path, recording, virtual environment, Phone Link pairing, or Tailscale credential enters the portable archive.
- Hardware claims require physical evidence. Phone Link cellular-call loopback remains **NOT TESTED** until it is tested on the target laptop/Redmi.

## Commands

- Software tests: `python -m unittest discover -s tests -v`
- Run development server: `python backend/server.py --port 8765`
- Android debug APK: `BUILD_ANDROID.bat`
- Transfer build: `PREPARE_TRANSFER.bat`

## Success criteria

- A clean copy runs `FIRST_RUN.bat`, `CONFIGURE.bat`, then `START_SCUT.bat` without Computer-A state.
- The control center exposes real local status, pairing, alerts, and diagnostics.
- The Android app pairs over authenticated WebSocket, heartbeats, acknowledges alerts, and alerts/vibrates.
- The complete software test suite and portability/package scans pass.
