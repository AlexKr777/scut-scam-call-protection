import { bodyObject, json, unsupported } from "../_shared/http.ts"
import { deviceForRequest, rest, touchDevice } from "../_shared/database.ts"

Deno.serve(async request => {
  if (request.method === "OPTIONS") return new Response(null, { headers: { "access-control-allow-origin": "*" } })
  if (request.method !== "POST") return json(405, { error: { code: "METHOD_NOT_ALLOWED" } })
  if (!(await bodyObject(request))) return json(422, { error: { code: "VALIDATION_ERROR" } })
  try {
    const device = await deviceForRequest(request)
    if (!device || !device.enabled || device.role !== "CONTROLLER") return json(403, { error: { code: "CONTROLLER_REQUIRED" } })
    const [settings, receivers] = await Promise.all([
      rest("system_settings?id=eq.true&select=active_controller_id,active_receiver_id,hardware_controls_enabled"),
      rest("devices?role=eq.RECEIVER&enabled=eq.true&revoked_at=is.null&select=id,display_name,last_seen_at,app_version&order=last_seen_at.desc.nullslast"),
    ])
    const setting = Array.isArray(settings) ? settings[0] as { active_controller_id?: string; active_receiver_id?: string | null; hardware_controls_enabled?: boolean } | undefined : undefined
    if (setting?.active_controller_id !== device.id) return json(403, { error: { code: "CONTROLLER_REQUIRED" } })
    await touchDevice(device.id)
    return json(200, {
      activeReceiverId: setting.active_receiver_id ?? null,
      hardwareControlsEnabled: setting.hardware_controls_enabled === true,
      receivers: Array.isArray(receivers) ? receivers.map((row: Record<string, unknown>) => ({ id: row.id, displayName: row.display_name, lastSeenAt: row.last_seen_at, appVersion: row.app_version })) : [],
    })
  } catch (error) { return unsupported(error) }
})
