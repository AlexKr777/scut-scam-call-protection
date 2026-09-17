import { bodyObject, json, unsupported } from "../_shared/http.ts"
import { deviceForRequest, rest, touchDevice } from "../_shared/database.ts"
import { exeAuthenticated } from "../_shared/security.ts"

function asIso(value: unknown): string | null {
  return typeof value === "string" && !Number.isNaN(Date.parse(value)) ? value : null
}

Deno.serve(async request => {
  if (request.method === "OPTIONS") return new Response(null, { headers: { "access-control-allow-origin": "*" } })
  if (request.method !== "POST") return json(405, { error: { code: "METHOD_NOT_ALLOWED" } })
  const body = await bodyObject(request)
  if (!body) return json(422, { error: { code: "VALIDATION_ERROR" } })
  try {
    const device = await deviceForRequest(request)
    if ((!device || !device.enabled) && !exeAuthenticated(request)) return json(401, { error: { code: "HISTORY_ACCESS_DENIED" } })
    const limit = Number.isSafeInteger(body.limit) ? Math.max(1, Math.min(Number(body.limit), 50)) : 25
    const cursor = body.cursor === undefined ? null : asIso(body.cursor)
    if (body.cursor !== undefined && !cursor) return json(422, { error: { code: "VALIDATION_ERROR" } })
    const before = cursor ? `&started_at=lt.${encodeURIComponent(cursor)}` : ""
    const result = await rest(`conversation_history?select=*&order=started_at.desc,id.desc&limit=${limit + 1}${before}`)
    const rows = Array.isArray(result) ? result as Array<Record<string, unknown>> : []
    const page = rows.slice(0, limit)
    if (device) await touchDevice(device.id)
    return json(200, {
      conversations: page.map(row => ({
        id: row.id,
        protectedReceiverId: row.protected_receiver_id,
        protectedReceiverName: row.protected_receiver_name,
        startedAt: row.started_at,
        endedAt: row.ended_at,
        durationSeconds: row.duration_seconds,
        lifecycleStatus: row.lifecycle_status,
        preview: row.preview,
        attentionState: row.attention_state,
        incidentId: row.incident_id,
        incidentState: row.incident_state,
      })),
      nextCursor: rows.length > limit ? page.at(-1)?.started_at ?? null : null,
    })
  } catch (error) { return unsupported(error) }
})
