# SCUT Controller → Receiver — post-redesign implementation note

Date: 2026-09-08

## Authority and invariants

The approved premium redesign remains the visual source of truth. The Controller → Receiver brief is authoritative for role, command, incident, Supabase, and FCM semantics. `NOMIC_DEPLOYMENT_V1` remains at threshold `0.6`; Whisper Quality V2 and the Windows Phone Link pipeline are not part of this milestone's modification scope.

## Verified post-redesign integration map

| Subsystem | Current files | Integration responsibility |
| --- | --- | --- |
| Local brain / status / Android WebSocket | `backend/services.py`, `backend/server.py`, `backend/config.py` | Add a separate control-plane adapter, session/incident state, command consumption and outbox without moving inference out of `ScutService`. Existing `transcript()`, `send_alert()`, pairing/auth/heartbeat, and event publish paths are the integration seams. |
| Locked inference/audio | `backend/hybrid_v1.py`, `backend/nomic_deployment_v1.py`, `backend/whisper_quality.py`, `backend/realtime_pipeline.py`, `backend/guarded_audio.py` | Read-only for this milestone except for receiving session/epoch metadata at the service boundary. |
| Desktop | `desktop/src/App.tsx`, `desktop/src/api/contracts.ts`, `desktop/src/api/live-event-reducer.ts`, `desktop/src/components/DevicesPage.tsx`, `SettingsPage.tsx`, `LiveTranscript.tsx`, `desktop/electron/{main.ts,preload.cts}` | Extend only through typed, allow-listed backend status/events. Devices gains actual Controller/Receiver/cloud readiness; Settings gains real transport diagnostics; Live Transcript gains real incident/clear state. |
| Android | `android/app/src/main/java/org/scut/app/{MainActivity.java,ScutService.java}`, `AndroidManifest.xml`, `android/app/build.gradle` | Preserve current foreground WebSocket pairing fallback. Add role-aware enrollment/controller behavior, FCM receiver path, notification/deep-link behavior, and Incident presentation. |
| Packaging | `desktop/package.json`, `desktop/electron/backend-process.ts`, `BUILD_ANDROID.bat` | Include only source/config templates; never package service-role, FCM, or master-password secrets. |

## Current capability truth

- There is no Supabase client, migration, Edge Function, project URL, publishable key, project reference, master-password verifier, Firebase Android configuration, FCM service account, or Firebase dependency in the repository or process environment.
- Existing Android alerts travel directly over the local authenticated WebSocket. They are real for the old pairing flow but are not FCM and cannot satisfy background FCM delivery.
- Existing `ScutService.transcript()` creates a local decision and can emit an Android alert. It has no durable session/incident model, decision epoch, alert cancellation, command idempotency, or outbox.
- Existing desktop History and Alerts are deliberately capability-gated because persistence is not yet present. They must only be enabled after the new backend adapter persists real incident state.

## Contract-first implementation order

1. Add `supabase/migrations` for `devices`, `system_settings`, `controller_commands`, `call_sessions`, `incidents`, and `incident_evidence`, with RLS, minimal grants, command/session expiry, idempotency, and Realtime publication. Add Edge Functions for enrollment, role reassignment, commands, and FCM dispatch; secrets stay in the Edge Function environment.
2. Add an environment-validated Python control-plane adapter and in-memory/local outbox. It will fail closed when cloud configuration is absent and will not affect the existing local alert pipeline.
3. Add session-bound `decision_epoch`, VETO suppression attribution, FORCE incident dedupe/merge, and focused backend tests before joining them to automatic alert dispatch.
4. Add typed desktop contracts/components only for fields emitted by the backend adapter.
5. Add Android role/FCM/Incident paths after the Firebase project configuration is available; retain existing local WebSocket behavior as an explicit fallback rather than pretending FCM is active.

## Required external configuration before a real Supabase/FCM deployment

These values are intentionally absent and must be supplied outside version control:

- Supabase project URL/reference and publishable key, plus a deployment authority for migrations and Edge Functions.
- Edge Function secrets: master-password verifier/hash configuration and FCM service-account/HTTP-v1 credentials.
- Firebase Android `google-services.json` for package `org.scut.app` (or equivalent project configuration) and a project with Cloud Messaging enabled.
- Two physical Android devices and permission to install the rebuilt APK for the acceptance flows required by the brief.

Until those exist, the only defensible state is **cloud control plane unavailable**. The product must not label it connected, invent enrollment, or claim FCM notification delivery.
