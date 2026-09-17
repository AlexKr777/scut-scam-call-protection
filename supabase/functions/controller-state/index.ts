import { bodyObject, json, unsupported } from "../_shared/http.ts"
import { deviceForRequest, rest, touchDevice } from "../_shared/database.ts"

Deno.serve(async request => {
  if (request.method === "OPTIONS") return new Response(null, { headers: { "access-control-allow-origin": "*" } })
  if (request.method !== "POST") return json(405, { error: { code: "METHOD_NOT_ALLOWED" } })
  if (!(await bodyObject(request) ?? {})) return json(422, { error: { code: "VALIDATION_ERROR" } })
  try {
    const device = await deviceForRequest(request)
    if (!device || !device.enabled) return json(401, { error: { code: "DEVICE_AUTH_DENIED" } })
    const rows = await rest("system_settings?id=eq.true&select=active_controller_id,active_receiver_id,hardware_controls_enabled")
    const setting = Array.isArray(rows) ? rows[0] as { active_controller_id: string | null; active_receiver_id: string | null; hardware_controls_enabled: boolean } : null
    if (!setting) throw new Error("missing settings")
    const ids = [setting.active_controller_id, setting.active_receiver_id].filter((id): id is string => Boolean(id))
    const named = ids.length ? await rest(`devices?id=in.(${ids.join(",")})&select=id,display_name,last_seen_at`) : []
    const devices = Array.isArray(named) ? named as Array<{ id: string; display_name: string; last_seen_at: string | null }> : []
    const friendly = (id: string | null) => devices.find(item => item.id === id)
    await touchDevice(device.id)
    return json(200, {
      state: setting.active_controller_id ? "CONTROLLER_ASSIGNED" : "NO_CONTROLLER",
      role: setting.active_controller_id === device.id ? "CONTROLLER" : "RECEIVER",
      isController: setting.active_controller_id === device.id,
      isActiveReceiver: setting.active_receiver_id === device.id,
      hardwareControlsEnabled: setting.hardware_controls_enabled,
      primaryPhone: friendly(setting.active_controller_id) ? { displayName: friendly(setting.active_controller_id)?.display_name, lastSeenAt: friendly(setting.active_controller_id)?.last_seen_at } : null,
      protectedPhone: friendly(setting.active_receiver_id) ? { displayName: friendly(setting.active_receiver_id)?.display_name, lastSeenAt: friendly(setting.active_receiver_id)?.last_seen_at } : null,
    })
  } catch (error) { return unsupported(error) }
})
