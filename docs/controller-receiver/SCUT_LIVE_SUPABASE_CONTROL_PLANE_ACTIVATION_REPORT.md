# SCUT live Supabase control-plane activation

Date: 2026-09-08

## Verdict

The SCUT Controller/Receiver Supabase control plane is live in a dedicated Central EU project and the configured Windows authority has completed a real authenticated command-cycle. This activates the existing implementation; it does not replace its incident authority, audio pipeline, NOMIC deployment, Whisper configuration, or completed product redesign.

## Project discovery and provisioning

- The previously linked project, `Phone app`, was inspected and rejected: its deployed functions were `telegram-webhook` and `reminders`, not SCUT. It was not modified.
- A separate project, `scut-hackathon` (ref `hbmhjyjlwhmjzmenvraa`), was created in Central EU (Frankfurt) through the authenticated Supabase CLI. No paid size or add-on was selected.
- Migration `202609080001_controller_receiver.sql` was applied once to that empty project. No migration repair, pull, history rewrite, or foreign-project schema change was used.

## Deployed cloud contract

All nine checked-in Edge Functions are active at version 1:

- `enroll-device`, `claim-controller`, `update-device`
- `controller-command`, `configure-system`
- `exe-commands`, `exe-sync`, `incident-detail`, `send-fcm`

The two SCUT-only server secrets were set through Supabase secrets management:

- a generated EXE-to-Edge token;
- the SHA-256 verifier required by the existing master-PIN contract.

No secret values, service-role key, device credential, master PIN, or Firebase material is present in this report, tracked source, APK, or desktop bundle.

The migrated SQL contract contains the required device, singleton system-settings, session, command, incident, evidence, transcript and rate-limit structures; partial active-controller uniqueness; command idempotency; command leasing; RLS enablement; direct-role grant revocation; and publication of `controller_commands` to `supabase_realtime`.

The Supabase CLI could not produce a database schema dump on this workstation because Docker Desktop is unavailable. The applied migration result and live Edge API behaviour were used instead. Direct anonymous REST reads of both `devices` and `system_settings` were denied with HTTP 401, and unauthenticated `exe-commands` was also denied with HTTP 401. The functions' service-role database access remained server-side.

## Windows authority activation

`.local/control_plane.json` was created only on this PC with the new project URL and generated EXE token. It is Git-ignored and ACL-restricted to the current Windows user. A real project backend launched against it and reported:

- health: `ok`, protocol v1;
- control plane: `AVAILABLE / CONFIGURED`;
- mode: `OFF`, risk: `SAFE / Protection off`;
- no live session and no claimed capture.

This preserves fail-closed semantics: cloud configuration alone does not invent audio, transcript, risk, incident, FCM delivery, or capture state.

## Controlled live command verification

The real deployed functions registered two explicitly labelled activation-test device records, re-claimed the controller with the configured verifier, assigned the receiver, and accepted a `FORCE` command. Hardware controls were immediately disabled again. The genuine Windows command worker then leased and resolved that command while no live call existed; its designed result was `NEUTRAL_TEST`, producing no incident or FCM delivery. A subsequent authenticated lease call returned zero pending/leased commands.

The active test controller/receiver records remain in the new project solely because no deletion/revocation API is part of the approved contract. They are not physical devices, controls are disabled, and a later real controller claim plus system configuration replaces the active assignment.

## Realtime and FCM truthfulness

The database publication for `controller_commands` is deployed. The current approved Windows implementation deliberately consumes commands through authenticated `exe-commands` polling (0.75-second worker), rather than a Supabase Realtime client subscription. The EXE holds neither a Supabase service key nor a Supabase JWT, so introducing a direct database subscription would violate the no-secret-in-EXE design. The live command-reception assertion therefore covers the real polling route and does **not** claim that a client Realtime subscription was established.

`send-fcm` is deployed and correctly failed closed with `409 FCM_NOT_REGISTERED` in the activation project. Firebase is not configured yet:

- no `FCM_SERVICE_ACCOUNT_JSON` Supabase secret was available;
- no active receiver has supplied a real FCM registration token;
- `android/app/google-services.json` is intentionally absent and Git-ignored;
- no physical Android handset was attached for notification, overlay, Accessibility volume-key, or acknowledgement review.

FCM acceptance, handset display, and acknowledgement are therefore not claimed.

## Verification

| Check | Result |
| --- | --- |
| Edge Function deployment | 9/9 active |
| Edge Function Deno checks | passed |
| Migration application | passed |
| Anonymous direct REST and unauthenticated EXE access | denied (HTTP 401) |
| Controller claim / receiver assignment / FORCE insertion | passed |
| Real Windows backend against live control plane | passed |
| Command lease completion | queue empty after worker processing |
| FCM without real registration | fail-closed: `FCM_NOT_REGISTERED` |
| Focused Python suite | 30 passed |
| Desktop Vitest | 35 passed / 10 files |
| Desktop typecheck and production build | passed |
| Android debug APK build | passed |
| Desktop production dependency audit | 0 vulnerabilities |

## Operator handoff

1. Start SCUT normally. The Windows backend will read the local, ACL-restricted control-plane file and report availability only while the Edge API is reachable.
2. On each real Android device, enter `https://hbmhjyjlwhmjzmenvraa.supabase.co` in the existing cloud enrolment flow. Enrol the protected handset as `RECEIVER`; enrol the controller handset with the master PIN; then use the real controller to select the receiver.
3. Before enabling hardware controls, provision Firebase for package `org.scut.app`: add the real `google-services.json` locally (never commit it), provide the corresponding server service-account JSON as `FCM_SERVICE_ACCOUNT_JSON` in Supabase, rebuild/install the APK, and verify its FCM token registration.
4. Perform the remaining two-device acceptance: real guarded Phone Link audio, receiver FCM/overlay display, controlled FORCE/VETO keys, VETO during the automatic hold, stale-decision rejection, exact incident detail fetch, and offline retry. These are hardware acceptance checks, not covered by the activation-test records.
