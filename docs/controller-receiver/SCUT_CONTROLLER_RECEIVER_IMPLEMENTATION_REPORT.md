# SCUT Controller / Receiver implementation report

Date: 2026-09-08

## Delivered implementation

- Added a Supabase migration for `devices`, singleton `system_settings`, controller commands, call sessions, incidents, incident evidence, transcript segments, enrollment rate limiting, RLS-denied direct access, command leases, idempotency keys, and service-role-only database functions.
- Added authenticated Edge Functions for enrollment, controller reassignment, receiver/controller system configuration, device/FCM registration, FORCE/VETO command ingestion, EXE command leasing and sync, exact incident retrieval, and FCM HTTP v1 delivery.
- Added the Windows-authoritative incident coordinator: one incident per live episode, FORCE deduplication, neutral no-call FORCE, `decision_epoch`, stale decision rejection after VETO, 1.5-second automatic hold, and real evidence-only sync.
- Added a fail-closed Windows control-plane adapter. It holds no Supabase service role or FCM secret, reports unavailable/degraded state truthfully, and retries bounded stable-ID sync/push records through `.local/control_plane_outbox.json` only when configured.
- Added Android controller enrollment/configuration, FCM token forwarding, data-payload incident handling, authenticated incident review, and an explicitly user-enabled Android Accessibility volume-key route (down = FORCE, up = VETO). The pre-existing local paired-WebSocket companion remains intact.
- Added desktop display of the Windows-reported command-plane state only; no synthetic cloud/device/session claims were introduced.

## Lock preservation

No changes were made to Whisper Quality V2 settings, NOMIC_DEPLOYMENT_V1 artefacts/threshold, the existing Phone Link capture logic, or the approved desktop/Android visual foundation.

## Local verification

| Check | Result |
|---|---|
| Controller/incident/service/server backend regression subset | 30 passed (Python 3.12 project runtime) |
| Controller adapter and incident unit coverage | included in the 30 passing tests |
| Deno type checks for all Edge Functions | passed |
| Desktop Vitest | 35 passed across 10 files |
| Desktop TypeScript + production Vite/Electron build | passed |
| Windows NSIS package | passed: `desktop/release/SCUT Setup 0.1.0.exe` |
| Android debug APK build | passed: `dist/SCUT.apk` |
| Real local backend runtime | `/health` returned `ok`, protocol v1; status truthfully returned `CONTROL_PLANE_NOT_CONFIGURED`, `OFF`, no live session |

The repository also has a prepared GPU Python runtime with the optional `numpy`, `torch`, and `scikit-learn` research dependencies. The smaller portable `.local/venv` intentionally lacks those optional research packages; command-plane tests and production backend tests pass there.

## External acceptance still required

No Supabase project credentials, Firebase service account, `android/app/google-services.json`, active FCM registration, or two physical Android devices were present in the workspace or environment. Consequently the following were **not** claimed as complete:

- applying the migration to a live Supabase project;
- deploying Edge Functions and injecting their secrets;
- actual FCM acceptance/display/acknowledgement;
- physical Accessibility key interception on a controller handset;
- two-phone FORCE/VETO/end-to-end acceptance during a verified Phone Link audio session.

These are deployment/physical-lab prerequisites, not mocked tests. The exact safe procedure is in [SCUT_CONTROL_PLANE_SETUP.md](./SCUT_CONTROL_PLANE_SETUP.md).

## Relevant commits

- `da8c086` authoritative incident core
- `926e760` secured command-plane schema
- `2ce471f` authenticated Supabase Edge Functions
- `73abc8a` Windows command authority
- `8f1c9d7` Android controller/receiver delivery paths
- `925856f` stable retry outbox
- `739646a` reassignment/order correctness fixes
- `1d2a712` automatic hold and VETO integration
