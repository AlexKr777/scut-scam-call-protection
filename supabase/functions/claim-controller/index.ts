import { bodyObject, json, requiredString, unsupported } from "../_shared/http.ts"
import { deviceForRequest, rpc, touchDevice } from "../_shared/database.ts"
import { masterPasswordAccepted, sha256 } from "../_shared/security.ts"

Deno.serve(async request => {
  if (request.method === "OPTIONS") return new Response(null, { headers: { "access-control-allow-origin": "*" } })
  if (request.method !== "POST") return json(405, { error: { code: "METHOD_NOT_ALLOWED" } })
  const body = await bodyObject(request)
  if (!body) return json(422, { error: { code: "VALIDATION_ERROR" } })
  try {
    const device = await deviceForRequest(request)
    const password = requiredString(body, "masterPassword", 512)
    if (!device || !device.enabled) return json(401, { error: { code: "DEVICE_AUTH_DENIED" } })
    const peer = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown"
    const allowed = await rpc("allow_enrollment", {
      p_key_hash: await sha256(`controller-claim:${peer}:${device.id}`),
      p_window_seconds: 300,
      p_limit: 5,
    })
    if (allowed !== true) return json(429, { error: { code: "ENROLLMENT_RATE_LIMITED" } })
    if (!password || !(await masterPasswordAccepted(password))) return json(403, { error: { code: "MASTER_PASSWORD_REQUIRED" } })
    const claimed = await rpc("claim_unassigned_controller", { p_device_id: device.id })
    if (claimed !== true) return json(409, { error: { code: "CONTROLLER_ALREADY_CLAIMED" } })
    await touchDevice(device.id)
    return json(200, { deviceId: device.id, role: "CONTROLLER" })
  } catch (error) {
    return unsupported(error)
  }
})
