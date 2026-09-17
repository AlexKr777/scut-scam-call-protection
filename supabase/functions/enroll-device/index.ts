import { bodyObject, json, requiredString, unsupported } from "../_shared/http.ts"
import { newCredential, masterPasswordAccepted, sha256 } from "../_shared/security.ts"
import { rest, rpc } from "../_shared/database.ts"

Deno.serve(async request => {
  if (request.method === "OPTIONS") return new Response(null, { headers: { "access-control-allow-origin": "*" } })
  if (request.method !== "POST") return json(405, { error: { code: "METHOD_NOT_ALLOWED" } })
  const body = await bodyObject(request)
  if (!body) return json(422, { error: { code: "VALIDATION_ERROR" } })
  try {
    const installId = requiredString(body, "installId", 128)
    const displayName = requiredString(body, "displayName", 96)
    const requestedRole = body.role === "CONTROLLER" ? "CONTROLLER" : "RECEIVER"
    const password = typeof body.masterPassword === "string" ? body.masterPassword : ""
    const peer = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown"
    if (!installId || !displayName || !(await rpc("allow_enrollment", { p_key_hash: await sha256(`${peer}:${installId}`), p_window_seconds: 300, p_limit: 5 }))) {
      return json(429, { error: { code: "ENROLLMENT_RATE_LIMITED" } })
    }
    if (requestedRole === "CONTROLLER" && !(await masterPasswordAccepted(password))) {
      return json(403, { error: { code: "MASTER_PASSWORD_REQUIRED" } })
    }
    const credential = newCredential()
    // Insert as a receiver before atomically promoting it. This lets a valid
    // master-password enrollment replace an existing active controller without
    // violating the one-controller partial unique index mid-transaction.
    const inserted = await rest("devices", { method: "POST", body: JSON.stringify({ install_id: installId, display_name: displayName, role: "RECEIVER", credential_hash: await sha256(credential), app_version: requiredString(body, "appVersion", 64) }) })
    const device = Array.isArray(inserted) ? inserted[0] as { id: string; role: string } : null
    if (!device) throw new Error("device insert returned no row")
    if (requestedRole === "CONTROLLER") await rpc("reassign_controller", { p_device_id: device.id })
    return json(201, { deviceId: device.id, role: requestedRole, credential })
  } catch (error) {
    return unsupported(error)
  }
})
