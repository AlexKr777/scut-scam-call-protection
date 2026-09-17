import { bodyObject, json, requiredString, unsupported } from "../_shared/http.ts"
import { deviceForRequest, touchDevice } from "../_shared/database.ts"

Deno.serve(async request => {
  if (request.method === "OPTIONS") return new Response(null, { headers: { "access-control-allow-origin": "*" } })
  if (request.method !== "POST") return json(405, { error: { code: "METHOD_NOT_ALLOWED" } })
  const body = await bodyObject(request)
  if (!body) return json(422, { error: { code: "VALIDATION_ERROR" } })
  try {
    const device = await deviceForRequest(request)
    if (!device || !device.enabled) return json(401, { error: { code: "DEVICE_AUTH_DENIED" } })
    const token = body.fcmRegistrationToken === undefined ? undefined : requiredString(body, "fcmRegistrationToken", 4096)
    const version = body.appVersion === undefined ? undefined : requiredString(body, "appVersion", 64)
    if ((body.fcmRegistrationToken !== undefined && !token) || (body.appVersion !== undefined && !version)) return json(422, { error: { code: "VALIDATION_ERROR" } })
    await touchDevice(device.id, { ...(token ? { fcm_registration_token: token } : {}), ...(version ? { app_version: version } : {}) })
    return json(200, { deviceId: device.id, role: device.role, registered: Boolean(token) })
  } catch (error) {
    return unsupported(error)
  }
})
