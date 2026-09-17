# SCUT Firebase / FCM activation

Date: 2026-09-09

## Verdict

The SCUT Firebase Cloud Messaging foundation is live for the existing Controller/Receiver Supabase control plane. It uses one dedicated Firebase Spark project and the existing `send-fcm` Edge Function; it does not introduce Firebase databases, Firebase Functions, Storage, Analytics, Gemini, a billing account, or a parallel control plane.

## Firebase project and Android identity

- Dedicated Firebase project: `scut-hackathon-684217`.
- Billing verification: no billing account is attached and `billingEnabled` is `false`.
- The project has one active Android app with the existing application ID `org.scut.app`.
- Firebase CLI generated `android/app/google-services.json` from that app. The file is Git-ignored and was verified to contain the matching Firebase project, Android package, and mobile SDK app ID.
- The real debug APK ran the Google Services Gradle task and has package ID `org.scut.app`.

## Server-side FCM

- Only `fcm.googleapis.com` is enabled for this milestone; it was already enabled by Firebase project setup.
- A dedicated SCUT FCM sender service account has only `roles/firebasecloudmessaging.admin`.
- Its current JSON key is stored only as the existing Supabase secret `FCM_SERVICE_ACCOUNT_JSON`; the JSON is neither tracked nor retained locally.
- A temporary superseded key was deleted from Google Cloud. Exactly one user-managed sender key remains, corresponding to the Supabase secret.
- `send-fcm` was redeployed to the dedicated live SCUT Supabase project `hbmhjyjlwhmjzmenvraa`. The unrelated `Phone app` Supabase project was not accessed or changed.
- A server credential OAuth smoke test passed. An authenticated FCM HTTP v1 call with an intentionally invalid registration token reached FCM and received HTTP `400`, proving authentication and the FCM endpoint path without sending a notification.

## Android token lifecycle

The Android client already refreshed an FCM token at startup and updated it through the authenticated `update-device` Edge Function. This activation adds a second refresh immediately after successful cloud enrolment, when the device credential has just been persisted. This closes the enrollment-order gap without persisting a Firebase credential, changing device roles, or changing FORCE, VETO, incidents, Whisper, NOMIC, Phone Link, or the completed Android visual system.

## Verification

| Check | Result |
| --- | --- |
| Firebase project discovery before creation | no accessible Firebase project |
| Dedicated Firebase project | active |
| Billing account | absent; disabled |
| Android package / generated configuration | `org.scut.app`; verified |
| FCM HTTP v1 API | enabled |
| OAuth service-account smoke test | passed |
| Authenticated FCM HTTP v1 invalid-token smoke test | passed; HTTP 400 from FCM |
| Supabase secret presence | verified by name only |
| Live `send-fcm` deployment | passed |
| Android debug build with Google Services task | passed |
| APK package identity | `org.scut.app` |
| APK server-secret material scan | passed |
| Focused backend control-plane regression suite | 30 passed |
| Desktop tests | 35 passed across 10 files |
| Desktop type check and production build | passed |
| Edge Function Deno checks | passed |
| ADB device discovery | no devices attached |

## Security and truthfulness

- No service-role credential, FCM service-account JSON, master PIN, or FCM registration token was added to tracked source, the APK, or documentation.
- `google-services.json` remains local and Git-ignored. Its Firebase client configuration is not treated as a server credential.
- FCM remains an acceleration/delivery channel only. Supabase remains the control-plane source of truth, and existing authenticated polling remains unchanged.
- No real receiver registration token or physical notification delivery was fabricated. The established `FCM_NOT_REGISTERED` fail-closed behavior remains correct until an enrolled physical receiver supplies its token.

## Physical-device acceptance still required

No ADB device was attached during this activation. The cloud side is ready, but the following must be accepted on real devices before claiming handset end-to-end delivery:

1. Install `dist/SCUT.apk` on the receiver and grant notification permission.
2. Enrol it through the existing authenticated SCUT cloud flow; the post-enrol token refresh registers its genuine FCM token.
3. Select it as the active receiver using the existing Controller flow.
4. Run the existing guarded call/incident scenario and verify the receiver notification and incident detail fetch.

Until that is performed, the accurate status is:

`SCUT_FIREBASE_FCM_CLOUD_READY_PHYSICAL_ACCEPTANCE_PENDING`
