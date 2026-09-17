import { bodyObject, json, unsupported } from "../_shared/http.ts"
import { deviceForRequest, rest, rpc, touchDevice } from "../_shared/database.ts"
import { exeAuthenticated } from "../_shared/security.ts"

Deno.serve(async request => {
  if (request.method === "OPTIONS") return new Response(null, { headers: { "access-control-allow-origin": "*" } })
  if (request.method !== "POST") return json(405, { error: { code: "METHOD_NOT_ALLOWED" } })
  await bodyObject(request)
  try {
    if (exeAuthenticated(request)) {
      const result = await rpc("release_controller", {})
      const value = Array.isArray(result) ? result[0] as { state?: string; had_controller?: boolean } : null
      return json(200, { state: value?.state === "NO_CONTROLLER" ? "NO_CONTROLLER" : "NO_CONTROLLER", released: value?.had_controller === true })
    }
    const device = await deviceForRequest(request)
    if (!device || !device.enabled || device.role !== "CONTROLLER") return json(403, { error: { code: "CONTROLLER_REQUIRED" } })
    const settings = await rest("system_settings?id=eq.true&select=active_controller_id")
    const current = Array.isArray(settings) ? settings[0] as { active_controller_id: string | null } : null
    if (current?.active_controller_id !== device.id) return json(403, { error: { code: "CONTROLLER_REQUIRED" } })
    const result = await rpc("release_controller", { p_expected_controller_id: device.id })
    const value = Array.isArray(result) ? result[0] as { released?: boolean } : null
    if (!value?.released) return json(403, { error: { code: "CONTROLLER_REQUIRED" } })
    await touchDevice(device.id)
    return json(200, { state: "NO_CONTROLLER", released: true })
  } catch (error) { return unsupported(error) }
})
