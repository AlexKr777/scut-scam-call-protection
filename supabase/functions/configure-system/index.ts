import { bodyObject, json, requiredString, unsupported } from "../_shared/http.ts"
import { deviceForRequest, rpc, touchDevice } from "../_shared/database.ts"

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

Deno.serve(async request => {
  if (request.method === "OPTIONS") return new Response(null, { headers: { "access-control-allow-origin": "*" } })
  if (request.method !== "POST") return json(405, { error: { code: "METHOD_NOT_ALLOWED" } })
  const body = await bodyObject(request)
  if (!body) return json(422, { error: { code: "VALIDATION_ERROR" } })
  try {
    const device = await deviceForRequest(request)
    const receiverId = requiredString(body, "activeReceiverId", 36)
    if (!device || !device.enabled || device.role !== "CONTROLLER") return json(403, { error: { code: "CONTROLLER_REQUIRED" } })
    if (!receiverId || !uuid.test(receiverId) || typeof body.hardwareControlsEnabled !== "boolean") return json(422, { error: { code: "VALIDATION_ERROR" } })
    await rpc("configure_system", { p_controller_id: device.id, p_receiver_id: receiverId, p_hardware_controls_enabled: body.hardwareControlsEnabled })
    await touchDevice(device.id)
    return json(200, { activeControllerId: device.id, activeReceiverId: receiverId, hardwareControlsEnabled: body.hardwareControlsEnabled })
  } catch (error) {
    return unsupported(error)
  }
})
