import { bodyObject, json, requiredString, unsupported } from "../_shared/http.ts"
import { rest } from "../_shared/database.ts"
import { exeAuthenticated } from "../_shared/security.ts"
import { sendIncidentFcm, sendNeutralFcm } from "../_shared/fcm.ts"

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

export async function handleSendFcm(request: Request): Promise<Response> {
  if (request.method === "OPTIONS") return new Response(null, { headers: { "access-control-allow-origin": "*" } })
  if (request.method !== "POST") return json(405, { error: { code: "METHOD_NOT_ALLOWED" } })
  const body = await bodyObject(request)
  if (!body) return json(422, { error: { code: "VALIDATION_ERROR" } })
  try {
    if (!exeAuthenticated(request)) return json(401, { error: { code: "EXE_AUTH_DENIED" } })
    const incidentId = requiredString(body, "incidentId", 36)
    const neutral = body.kind === "NEUTRAL_TEST"
    const commandId = requiredString(body, "commandId", 36)
    if (neutral ? (!commandId || !uuid.test(commandId) || body.incidentId !== undefined)
      : (body.kind !== undefined || !incidentId || !uuid.test(incidentId))) return json(422, { error: { code: "VALIDATION_ERROR" } })
    const settings = await rest("system_settings?id=eq.true&select=active_receiver_id")
    const receiverId = Array.isArray(settings) ? (settings[0] as { active_receiver_id: string | null } | undefined)?.active_receiver_id : null
    if (!receiverId) return json(409, { error: { code: "NO_ACTIVE_RECEIVER" } })
    const devices = await rest(`devices?id=eq.${receiverId}&enabled=is.true&revoked_at=is.null&select=fcm_registration_token`)
    const token = Array.isArray(devices) ? (devices[0] as { fcm_registration_token: string | null } | undefined)?.fcm_registration_token : null
    if (!token) return json(409, { error: { code: "FCM_NOT_REGISTERED" } })
    if (neutral) {
      const messageId = await sendNeutralFcm(token, commandId!)
      return json(202, { kind: "NEUTRAL_TEST", commandId, messageId })
    }
    const messageId = await sendIncidentFcm(token, incidentId!)
    await rest(`incidents?id=eq.${incidentId}`, { method: "PATCH", body: JSON.stringify({ notification_message_id: messageId, updated_at: new Date().toISOString() }) })
    return json(202, { incidentId, messageId })
  } catch (error) {
    return unsupported(error)
  }
}

if (import.meta.main) Deno.serve(handleSendFcm)
