import { bodyObject, json, requiredString, unsupported } from "../_shared/http.ts"
import { deviceForRequest, rest, touchDevice } from "../_shared/database.ts"

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

Deno.serve(async request => {
  if (request.method === "OPTIONS") return new Response(null, { headers: { "access-control-allow-origin": "*" } })
  if (request.method !== "POST") return json(405, { error: { code: "METHOD_NOT_ALLOWED" } })
  const body = await bodyObject(request)
  if (!body) return json(422, { error: { code: "VALIDATION_ERROR" } })
  try {
    const device = await deviceForRequest(request)
    if (!device || !device.enabled || device.role !== "CONTROLLER") return json(403, { error: { code: "CONTROLLER_REQUIRED" } })
    const settings = await rest("system_settings?id=eq.true&select=active_controller_id,hardware_controls_enabled")
    const setting = Array.isArray(settings) ? settings[0] as { active_controller_id: string | null; hardware_controls_enabled: boolean } : null
    if (!setting?.hardware_controls_enabled || setting.active_controller_id !== device.id) return json(403, { error: { code: "HARDWARE_CONTROLS_DISABLED" } })
    const command = requiredString(body, "command", 12)
    const sequence = body.clientSequence
    const sessionId = body.sessionId === undefined ? null : requiredString(body, "sessionId", 36)
    if ((command !== "FORCE" && command !== "VETO") || !Number.isSafeInteger(sequence) || (sessionId && !uuid.test(sessionId))) return json(422, { error: { code: "VALIDATION_ERROR" } })
    const now = Date.now()
    const inserted = await rest("controller_commands", { method: "POST", body: JSON.stringify({ controller_id: device.id, command_type: command, client_sequence: sequence, session_id: sessionId, decision_epoch: Number.isSafeInteger(body.decisionEpoch) ? body.decisionEpoch : null, expires_at: new Date(now + 20_000).toISOString() }) })
    const value = Array.isArray(inserted) ? inserted[0] as { id: string; received_at: string } : null
    if (!value) throw new Error("controller command insert returned no row")
    await touchDevice(device.id)
    return json(202, { commandId: value.id, receivedAt: value.received_at })
  } catch (error) {
    const detail = error instanceof Error ? error.message : ""
    if (detail.includes("duplicate key")) return json(409, { error: { code: "DUPLICATE_COMMAND" } })
    return unsupported(error)
  }
})
