import { handleSendFcm } from "./index.ts"

function assert(condition: unknown, message = "Assertion failed"): asserts condition {
  if (!condition) throw new Error(message)
}

Deno.test("authenticated neutral push reaches Firebase with active receiver token and never touches incidents", async () => {
  const keys = ["SCUT_EXE_CONTROL_TOKEN", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "FCM_SERVICE_ACCOUNT_JSON"]
  const previous = keys.map(key => Deno.env.get(key))
  const originalFetch = globalThis.fetch
  const pair = await crypto.subtle.generateKey({ name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" }, true, ["sign", "verify"])
  const privateKey = btoa(String.fromCharCode(...new Uint8Array(await crypto.subtle.exportKey("pkcs8", pair.privateKey))))
  const values = ["test-exe-secret", "https://test.supabase.co", "test-server-key", JSON.stringify({ client_email: "test@example.com", project_id: "test-project", private_key: privateKey })]
  keys.forEach((key, index) => Deno.env.set(key, values[index]))
  const paths: string[] = []
  let receiver: string | null = "receiver-1"
  let token: string | null = "active-receiver-token"
  let fcmStatus = 200
  let sent: Record<string, any> = {}
  globalThis.fetch = async (input, init) => {
    const url = String(input)
    paths.push(url)
    assert(!url.includes("incidents"), "Neutral test must not read or write incidents")
    if (url.includes("system_settings?")) return Response.json([{ active_receiver_id: receiver }])
    if (url.includes("devices?")) {
      assert(url.includes("id=eq.receiver-1&enabled=is.true&revoked_at=is.null"))
      return Response.json([{ fcm_registration_token: token }])
    }
    if (url === "https://oauth2.googleapis.com/token") return Response.json({ access_token: "test-oauth" })
    assert(url === "https://fcm.googleapis.com/v1/projects/test-project/messages:send")
    sent = JSON.parse(String(init?.body)).message
    return Response.json(fcmStatus === 200 ? { name: "projects/test-project/messages/accepted" } : { error: { status: "UNREGISTERED" } }, { status: fcmStatus })
  }
  const body = { kind: "NEUTRAL_TEST", commandId: "00000000-0000-4000-8000-000000000001" }
  const request = (payload: unknown = body, secret = "test-exe-secret") => new Request("https://test/send-fcm", { method: "POST", headers: { "content-type": "application/json", "x-scut-exe-token": secret }, body: JSON.stringify(payload) })
  try {
    assert((await handleSendFcm(request(body, "wrong"))).status === 401)
    assert((await handleSendFcm(request({ ...body, incidentId: body.commandId }))).status === 422)
    assert((await handleSendFcm(request({ ...body, commandId: "invalid" }))).status === 422)
    assert(paths.length === 0)
    const response = await handleSendFcm(request())
    assert(response.status === 202)
    assert((await response.json()).messageId === "projects/test-project/messages/accepted")
    assert(sent.token === "active-receiver-token")
    assert(sent.data.kind === "NEUTRAL_TEST" && sent.data.commandId === body.commandId)
    assert(sent.data.title === "SCUT подключён")
    assert(sent.data.body === "Активного звонка сейчас нет. Связь между устройствами работает.")
    assert(!("incidentId" in sent.data) && !("deepLink" in sent.data))
    assert(sent.android.priority === "high")
    receiver = null
    assert((await handleSendFcm(request())).status === 409)
    receiver = "receiver-1"; token = null
    assert((await handleSendFcm(request())).status === 409)
    token = "expired-token"; fcmStatus = 404
    assert((await handleSendFcm(request())).status === 503)
  } finally {
    globalThis.fetch = originalFetch
    keys.forEach((key, index) => previous[index] === undefined ? Deno.env.delete(key) : Deno.env.set(key, previous[index]!))
  }
})
