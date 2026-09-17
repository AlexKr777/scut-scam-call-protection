import { bodyObject, json, unsupported } from "../_shared/http.ts"
import { rpc } from "../_shared/database.ts"
import { exeAuthenticated } from "../_shared/security.ts"

Deno.serve(async request => {
  if (request.method === "OPTIONS") return new Response(null, { headers: { "access-control-allow-origin": "*" } })
  if (request.method !== "POST") return json(405, { error: { code: "METHOD_NOT_ALLOWED" } })
  try {
    if (!exeAuthenticated(request)) return json(401, { error: { code: "EXE_AUTH_DENIED" } })
    const body = await bodyObject(request) ?? {}
    const limit = Number.isSafeInteger(body.limit) ? Math.max(1, Math.min(64, body.limit as number)) : 16
    const commands = await rpc("claim_controller_commands", { p_limit: limit })
    return json(200, { commands: Array.isArray(commands) ? commands : [] })
  } catch (error) {
    return unsupported(error)
  }
})
