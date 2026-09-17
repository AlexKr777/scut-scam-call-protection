# Controller / Receiver control plane setup

This repository contains the schema and Edge Function code, but it deliberately contains no Supabase project, Firebase project, service account, master-password verifier, or device credentials. Until these are provisioned, SCUT reports `CONTROL_PLANE_NOT_CONFIGURED`; it does not claim that controller commands or FCM are active.

## 1. Provision Supabase

Create a Supabase project, then authenticate and link its project reference before applying the checked-in migration:

```powershell
supabase.cmd login
supabase.cmd link --project-ref <project-ref>
supabase.cmd db push
```

Generate a high-entropy Windows-to-Edge token and a SHA-256 verifier for the master password outside the repository. Store Edge secrets only through the Supabase CLI/dashboard:

```powershell
supabase.cmd secrets set SCUT_EXE_CONTROL_TOKEN=<random-secret>
supabase.cmd secrets set SCUT_MASTER_PASSWORD_SHA256=<sha256-of-master-password>
supabase.cmd secrets set FCM_SERVICE_ACCOUNT_JSON='<service-account-json-on-one-line>'
supabase.cmd functions deploy enroll-device claim-controller update-device controller-command configure-system exe-commands exe-sync incident-detail send-fcm
```

The functions use the server-side `SUPABASE_SERVICE_ROLE_KEY` supplied by the platform. Do not add that key to the EXE, Android project, a `.local` file, or source control. All exposed tables have RLS enabled and no direct `anon`/`authenticated` grants.

## 2. Configure the Windows authority

On the Windows PC only, create `.local/control_plane.json`; it is ignored by Git and its ACL is restricted when SCUT writes retry state:

```json
{
  "url": "https://<project-ref>.supabase.co",
  "exeToken": "the-same-random-secret-set-as-SCUT_EXE_CONTROL_TOKEN"
}
```

Environment variables `SCUT_SUPABASE_URL` and `SCUT_EXE_CONTROL_TOKEN` take precedence. The EXE starts a command poller only as an adapter: it remains the authority for sessions, `decision_epoch`, incident identity, and VETO ordering.

## 3. Configure Firebase / Android

Register Android package `org.scut.app` in the Firebase project that owns the FCM service account. Download its `google-services.json` to `android/app/google-services.json`; it is ignored and must never be committed. Build and install the APK, approve Android notification permission, then enroll both devices in the app:

1. Enroll the protected device as `RECEIVER`; record its displayed device ID.
2. Enroll the control phone as `CONTROLLER` using the master password. The password is transmitted to the Edge Function only for this operation and is not saved locally.
3. On the controller, set that receiver device ID, enable hardware controls, and explicitly enable **SCUT Controller buttons** in Android Accessibility settings.

When hardware controls are enabled, Volume Down submits `FORCE` and Volume Up submits `VETO`. When disabled or the accessibility service is not enabled, those buttons retain normal Android behavior. A data-only FCM payload carries a stable incident ID; the Android app fetches the exact incident through its authenticated Edge Function rather than presenting invented evidence or delivery acknowledgement.

## 4. Required real-device review

Verify on two physical Android devices and the Windows authority: controller enrollment, receiver FCM token registration, hardware FORCE during live guarded audio, repeated FORCE deduplication, VETO during the automatic hold, stale decision rejection, incident deep-link, and retry after temporarily disconnecting Supabase. FCM acceptance is not proof of handset display or user acknowledgement.
