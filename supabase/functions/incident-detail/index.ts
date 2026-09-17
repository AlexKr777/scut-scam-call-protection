import { bodyObject, json, requiredString, unsupported } from "../_shared/http.ts"
import { deviceForRequest, rest, touchDevice } from "../_shared/database.ts"
import { exeAuthenticated } from "../_shared/security.ts"

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

Deno.serve(async request => {
  if (request.method === "OPTIONS") return new Response(null, { headers: { "access-control-allow-origin": "*" } })
  if (request.method !== "POST") return json(405, { error: { code: "METHOD_NOT_ALLOWED" } })
  const body = await bodyObject(request)
  if (!body) return json(422, { error: { code: "VALIDATION_ERROR" } })
  try {
    const device = await deviceForRequest(request)
    const incidentId = requiredString(body, "incidentId", 36)
    if ((!device || !device.enabled) && !exeAuthenticated(request)) return json(401, { error: { code: "INCIDENT_ACCESS_DENIED" } })
    if (!incidentId || !uuid.test(incidentId)) return json(422, { error: { code: "VALIDATION_ERROR" } })
    const incidents = await rest(`incidents?id=eq.${incidentId}&select=id,session_id,state,source,created_at,updated_at,incident_evidence(id,evidence_type,occurred_at,payload)`)
    const incident = Array.isArray(incidents) ? incidents[0] : null
    if (!incident) return json(404, { error: { code: "INCIDENT_NOT_FOUND" } })
    if (device) await touchDevice(device.id)
    return json(200, { incident })
  } catch (error) {
    return unsupported(error)
  }
})
