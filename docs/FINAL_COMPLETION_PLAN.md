# SCUT remaining gates completion plan

## Authority and constraints

The user approved Gate C and explicitly authorized all remaining phases without further approval gates. The master brief remains authoritative. Backend business logic, Android pairing/authentication/alert behavior, and real-data constraints are preserved.

## Ordered vertical slices

1. **Gate D — desktop capability surfaces.** Add typed, allow-listed Electron bridge operations for existing diagnostics/pairing endpoints; implement Devices and Settings › Diagnostics; add capability-gated History and Alerts empty surfaces. Test bridge-facing view models and page interactions; build and runtime-review.
2. **Gate E — Android UI layer.** Preserve `ScutService` protocol and foreground behavior while replacing the activity/overlay presentation with the cream/green SCUT system. Build the debug APK and run repository Android checks.
3. **Gate F — Windows distribution.** Add reproducible Electron packaging, installer configuration, source/runtime prerequisite detection, build scripts, and recovery guidance. Build the installer/portable artifact available on this workstation; cold-start it when feasible.
4. **Gate G — final QA and demo hardening.** Run desktop/backend/Android/portability suites; production builds; runtime health and safe diagnostic flow; screenshot reviews for desktop DPI states; audit copied artifacts and truthfulness constraints; write the consolidated report.

## Risks and defaults

- Existing backend has no persistent history/alert records, manual-alert action, or continuous Phone Link call lifecycle. Those desktop surfaces remain explicitly capability-gated; no fake list or control is added.
- Android build depends on locally installed JDK/SDK/Gradle. If unavailable, the exact environmental blocker and existing `BUILD_ANDROID.bat` requirement are reported; source changes remain buildable.
- Installer packaging does not silently bundle user credentials, recordings, model assets, or an uncontrolled Python venv. Runtime prerequisites are declared and checked instead.
