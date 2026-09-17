# Desktop and mobile capabilities

## Desktop

| Capability | Finding |
|---|---|
| Packaging/current UI | Browser opened to a local Python service; no native desktop shell |
| Custom chrome, frameless/transparent window, tray, multi-window, always-on-top, startup at login, global hotkeys | NOT IMPLEMENTED / no wrapper code found |
| Native Windows integration | YES: C++ Core Audio helper executables and PowerShell discovery; controlled by backend |
| Native Windows notifications | NOT IMPLEMENTED; only Android notification implementation found |
| Local web UI / backend lifecycle | YES; startup PowerShell launches server and browser (`scripts/start-scut.ps1:1-10`) |

A future polished Windows desktop application requires a new wrapper/native UI layer; nothing in this repository establishes whether a chosen wrapper is compatible beyond its ability to talk to local REST/WebSocket.

## Android companion — VERIFIED

Android is a minimal pairing and alert receiver, not call-audio capture. It accepts a pasted pairing payload, persists endpoint/credential in `SharedPreferences`, runs a foreground WebSocket reconnect loop, heartbeats every 10 seconds, then displays native notification/vibration and an optional 12-second overlay for alert events (`android/app/src/main/java/org/scut/app/MainActivity.java:17-24`, `android/app/src/main/java/org/scut/app/ScutService.java:14-27`). Manifest requests Internet, vibration, notifications, foreground service and overlay permission (`android/app/src/main/AndroidManifest.xml:1-10`).

There is no mobile history, alert dismissal action, transcript view, account/authentication beyond pairing credential, or phone call/audio access. Cleartext WebSocket is permitted by manifest; transport security outside a Tailscale-style network is not established by repository evidence.
