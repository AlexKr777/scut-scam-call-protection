import { bodyObject, json, requiredString, unsupported } from "../_shared/http.ts"
import { rest } from "../_shared/database.ts"
import { exeAuthenticated } from "../_shared/security.ts"

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const incidentStates = new Set(["PENDING_FORCE", "PENDING_AUTO", "CONFIRMED", "USER_DISMISSED", "CLEARED"])

function iso(value: unknown): string | null {
  if (typeof value !== "string" || Number.isNaN(Date.parse(value))) return null
  return value
}

Deno.serve(async request => {
  if (request.method === "OPTIONS") return new Response(null, { headers: { "access-control-allow-origin": "*" } })
  if (request.method !== "POST") return json(405, { error: { code: "METHOD_NOT_ALLOWED" } })
  const body = await bodyObject(request)
  if (!body) return json(422, { error: { code: "VALIDATION_ERROR" } })
  try {
    if (!exeAuthenticated(request)) return json(401, { error: { code: "EXE_AUTH_DENIED" } })
    const kind = body.kind
    if (kind === "session") {
      const id = requiredString(body, "id", 36), startedAt = iso(body.startedAt), endedAt = body.endedAt === undefined ? null : iso(body.endedAt)
      if (!id || !uuid.test(id) || !startedAt || (body.endedAt !== undefined && !endedAt) || !Number.isSafeInteger(body.decisionEpoch) || (body.state !== "ACTIVE" && body.state !== "ENDED")) return json(422, { error: { code: "VALIDATION_ERROR" } })
      const settings = await rest("system_settings?id=eq.true&select=active_receiver_id")
      const activeReceiverId = Array.isArray(settings) ? (settings[0] as { active_receiver_id?: string | null } | undefined)?.active_receiver_id ?? null : null
      await rest("call_sessions?on_conflict=id", { method: "POST", headers: { prefer: "resolution=merge-duplicates,return=representation" }, body: JSON.stringify({ id, protected_receiver_id: activeReceiverId, started_at: startedAt, ended_at: endedAt, decision_epoch: body.decisionEpoch, state: body.state, updated_at: new Date().toISOString() }) })
      return json(200, { synced: "session", id })
    }
    if (kind === "transcript") {
      const sessionId = requiredString(body, "sessionId", 36), eventId = requiredString(body, "eventId", 36), text = requiredString(body, "text", 6000), endedAt = iso(body.endedAt)
      if (!sessionId || !eventId || !uuid.test(sessionId) || !uuid.test(eventId) || !text || !endedAt || !Number.isSafeInteger(body.sequence) || Number(body.sequence) < 0) return json(422, { error: { code: "VALIDATION_ERROR" } })
      await rest("transcript_segments?on_conflict=client_event_id", { method: "POST", headers: { prefer: "resolution=ignore-duplicates,return=representation" }, body: JSON.stringify({ client_event_id: eventId, session_id: sessionId, sequence: body.sequence, text, speaker: requiredString(body, "speaker", 32), started_at: iso(body.startedAt), ended_at: endedAt }) })
      return json(201, { synced: "transcript" })
    }
    if (kind === "incident") {
      const id = requiredString(body, "id", 36), sessionId = requiredString(body, "sessionId", 36), state = requiredString(body, "state", 32)
      const source = requiredString(body, "source", 12), createdAt = iso(body.createdAt), updatedAt = iso(body.updatedAt)
      if (!id || !sessionId || !uuid.test(id) || !uuid.test(sessionId) || !state || !incidentStates.has(state) || !source || !["FORCE", "AUTO", "MERGED"].includes(source) || !createdAt || !updatedAt || !Number.isSafeInteger(body.decisionEpoch) || !Number.isSafeInteger(body.forceCount)) return json(422, { error: { code: "VALIDATION_ERROR" } })
      await rest("incidents?on_conflict=id", { method: "POST", headers: { prefer: "resolution=merge-duplicates,return=representation" }, body: JSON.stringify({ id, session_id: sessionId, state, source, created_at: createdAt, updated_at: updatedAt, decision_epoch: body.decisionEpoch, force_count: body.forceCount }) })
      return json(200, { synced: "incident", id })
    }
    if (kind === "evidence") {
      const incidentId = requiredString(body, "incidentId", 36), eventId = requiredString(body, "eventId", 36), evidenceType = requiredString(body, "evidenceType", 16), occurredAt = iso(body.occurredAt)
      if (!incidentId || !eventId || !uuid.test(incidentId) || !uuid.test(eventId) || !evidenceType || !["TRANSCRIPT", "DECISION", "COMMAND"].includes(evidenceType) || !occurredAt || !body.payload || typeof body.payload !== "object" || Array.isArray(body.payload)) return json(422, { error: { code: "VALIDATION_ERROR" } })
      await rest("incident_evidence?on_conflict=client_event_id", { method: "POST", headers: { prefer: "resolution=ignore-duplicates,return=representation" }, body: JSON.stringify({ client_event_id: eventId, incident_id: incidentId, evidence_type: evidenceType, occurred_at: occurredAt, payload: body.payload }) })
      return json(201, { synced: "evidence" })
    }
    if (kind === "command-result") {
      const id = requiredString(body, "id", 36), state = requiredString(body, "state", 12)
      const validState = state !== null && ["APPLIED", "REJECTED", "EXPIRED"].includes(state)
      if (!id || !uuid.test(id) || !validState) return json(422, { error: { code: "VALIDATION_ERROR" } })
      const commandState = state as "APPLIED" | "REJECTED" | "EXPIRED"
      await rest(`controller_commands?id=eq.${id}&state=eq.LEASED`, { method: "PATCH", body: JSON.stringify({ state: commandState, applied_at: new Date().toISOString(), lease_expires_at: null, rejection_reason: requiredString(body, "reason", 160) }) })
      return json(200, { synced: "command-result", id })
    }
    return json(422, { error: { code: "VALIDATION_ERROR" } })
  } catch (error) {
    return unsupported(error)
  }
})
