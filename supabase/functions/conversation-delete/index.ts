import { bodyObject, json, requiredString, unsupported } from "../_shared/http.ts"
import { deviceForRequest, rpc, touchDevice } from "../_shared/database.ts"
import { exeAuthenticated } from "../_shared/security.ts"

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

Deno.serve(async request => {
  if (request.method === "OPTIONS") return new Response(null, { headers: { "access-control-allow-origin": "*" } })
  if (request.method !== "POST") return json(405, { error: { code: "METHOD_NOT_ALLOWED" } })
  const body = await bodyObject(request)
  if (!body) return json(422, { error: { code: "VALIDATION_ERROR" } })
  try {
    const device = await deviceForRequest(request)
    const id = requiredString(body, "conversationId", 36)
    if ((!device || !device.enabled) && !exeAuthenticated(request)) return json(401, { error: { code: "HISTORY_ACCESS_DENIED" } })
    if (!id || !uuid.test(id)) return json(422, { error: { code: "VALIDATION_ERROR" } })
    const result = await rpc("delete_conversation_history", { p_session_id: id })
    const deleted = result === true || (Array.isArray(result) && result[0] === true)
    if (device) await touchDevice(device.id)
    return json(200, { deleted })
  } catch (error) { return unsupported(error) }
})
