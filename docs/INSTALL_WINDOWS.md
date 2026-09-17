# Install SCUT on Windows

`desktop/release/SCUT Setup 0.1.0.exe` is a native NSIS installer for the Electron desktop shell. It installs a Start-menu and desktop shortcut; it does not open a browser.

## Prerequisites for real protection

The installer includes the desktop renderer and the authoritative Python backend source. It deliberately does **not** bundle a model cache, API secret, or a large Python environment: those are machine-specific and may be several gigabytes.

Before first launch, provide one compatible local Python runtime with SCUT's backend dependencies and, if required by the chosen model/runtime, its already-authorized local model cache. Either set `SCUT_PYTHON_PATH` to that runtime's `python.exe`, or make Python 3.12 available through the Windows `py` launcher. A development/portable checkout may instead retain its `.local\venv` beside `backend`.

The app fails closed when no compatible runtime starts: it remains usable as a shell, but reports that the backend is unavailable rather than inventing protection state. For the repository's tested portable setup, follow `FIRST_RUN.bat`, `CONFIGURE.bat`, then `START_SCUT.bat` as documented in the root README.

## Android companion

Install `dist/SCUT.apk` on Android 8.0 or newer, then create a pairing payload from **Devices** in the Windows app. Android only receives authenticated alerts from its paired PC; it does not claim cellular-call audio capture.
