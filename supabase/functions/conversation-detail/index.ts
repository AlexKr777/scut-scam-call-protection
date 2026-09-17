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
    const id = requiredString(body, "conversationId", 36)
    if ((!device || !device.enabled) && !exeAuthenticated(request)) return json(401, { error: { code: "HISTORY_ACCESS_DENIED" } })
    if (!id || !uuid.test(id)) return json(422, { error: { code: "VALIDATION_ERROR" } })
    const select = "id,protected_receiver_id,started_at,ended_at,state,devices!call_sessions_protected_receiver_id_fkey(display_name),transcript_segments(id,sequence,text,speaker,ended_at),incidents(id,state,source,created_at,updated_at,incident_evidence(id,evidence_type,occurred_at,payload))"
    const result = await rest(`call_sessions?id=eq.${id}&deleted_at=is.null&select=${select}&transcript_segments.order=sequence.asc`)
    const row = Array.isArray(result) ? result[0] as Record<string, unknown> | undefined : undefined
    if (!row) return json(404, { error: { code: "CONVERSATION_NOT_FOUND" } })
    if (device) await touchDevice(device.id)
    return json(200, {
      conversation: {
        id: row.id,
        protectedReceiverId: row.protected_receiver_id,
        protectedReceiverName: (row.devices as { display_name?: string } | null)?.display_name ?? null,
        startedAt: row.started_at,
        endedAt: row.ended_at,
        lifecycleStatus: row.state,
        segments: row.transcript_segments,
        incidents: row.incidents,
      },
    })
  } catch (error) { return unsupported(error) }
})
