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
    if ((!device || !device.enabled) && !exeAuthenticated(request)) return json(401, { error: { code: "ALERTS_ACCESS_DENIED" } })
    const limit = Number.isSafeInteger(body.limit) ? Math.max(1, Math.min(Number(body.limit), 50)) : 25
    const cursor = body.cursor === undefined ? null : asIso(body.cursor)
    if (body.cursor !== undefined && !cursor) return json(422, { error: { code: "VALIDATION_ERROR" } })
    const before = cursor ? `&updated_at=lt.${encodeURIComponent(cursor)}` : ""
    const result = await rest(`alert_history?select=*&order=updated_at.desc,id.desc&limit=${limit + 1}${before}`)
    const rows = Array.isArray(result) ? result as Array<Record<string, unknown>> : []
    const page = rows.slice(0, limit)
    if (device) await touchDevice(device.id)
    return json(200, {
      alerts: page.map(row => ({
        id: row.id,
        conversationId: row.conversation_id,
        state: row.state,
        source: row.source,
        createdAt: row.created_at,
        updatedAt: row.updated_at,
        conversationDeleted: row.conversation_deleted,
        conversationPreview: row.conversation_preview,
      })),
      nextCursor: rows.length > limit ? page.at(-1)?.updated_at ?? null : null,
    })
  } catch (error) { return unsupported(error) }
})
