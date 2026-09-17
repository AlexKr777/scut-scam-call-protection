# SCUT Controller release and reassignment

## NO_CONTROLLER

`NO_CONTROLLER` is an authoritative cloud state: `system_settings.active_controller_id` is null. Devices remain enrolled, the active Receiver and incident history remain unchanged, and hardware controls are disabled until a Controller is claimed again.

## Operator release

On the trusted Windows machine that already holds the ACL-restricted `.local/control_plane.json`, run:

```powershell
py.exe -3.12 scripts\scut_admin.py release-controller
```

The helper calls the protected `release-controller` Edge Function using the existing EXE token. It never requires a Supabase service-role key, never prints secrets or device identifiers, and is idempotent.

## Phone reassignment

Every enrolled phone refreshes `controller-state`. When it reports `NO_CONTROLLER`, SCUT displays the Russian claim panel and accepts a PIN only through the authenticated `claim-controller` Edge Function. The PIN is verified server-side; it is not stored in the APK, notification payloads, logs, or responses.

The database serializes claims by locking the singleton settings row. The first valid PIN claim wins. A concurrent valid claimant receives `CONTROLLER_ALREADY_CLAIMED` and stays a Receiver.

## Authority and recovery

Release demotes the old Controller to a normal Receiver, rejects its pending/leased commands, clears the active controller pointer, and disables hardware controls. Already applied actions are not undone. Controller-only commands and system configuration from the old credential fail immediately. The old installation remains registered and may claim again through the same PIN flow.

To inspect the state, open an enrolled app (it calls `controller-state`) or run the release helper: its idempotent output reports `NO_CONTROLLER` without exposing an ID. If a Controller phone is lost, release it through the trusted Windows helper and let the replacement enrolled phone claim using the server-verified PIN.
