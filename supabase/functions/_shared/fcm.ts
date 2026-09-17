import { configured } from "./http.ts"

type ServiceAccount = { client_email: string; private_key: string; project_id: string; token_uri?: string }
const encoder = new TextEncoder()

function base64Url(value: Uint8Array | string): string {
  const bytes = typeof value === "string" ? encoder.encode(value) : value
  let binary = ""
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "")
}

function pemBytes(pem: string): Uint8Array {
  const normalized = pem.replace(/-----BEGIN PRIVATE KEY-----|-----END PRIVATE KEY-----|\s/g, "")
  const binary = atob(normalized)
  return Uint8Array.from(binary, character => character.charCodeAt(0))
}

async function accessToken(account: ServiceAccount): Promise<string> {
  const now = Math.floor(Date.now() / 1000)
  const encodedHeader = base64Url(JSON.stringify({ alg: "RS256", typ: "JWT" }))
  const encodedClaims = base64Url(JSON.stringify({ iss: account.client_email, scope: "https://www.googleapis.com/auth/firebase.messaging", aud: account.token_uri ?? "https://oauth2.googleapis.com/token", iat: now, exp: now + 3600 }))
  const keyData = Uint8Array.from(pemBytes(account.private_key)).buffer as ArrayBuffer
  const key = await crypto.subtle.importKey("pkcs8", keyData, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["sign"])
  const signature = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, encoder.encode(`${encodedHeader}.${encodedClaims}`))
  const assertion = `${encodedHeader}.${encodedClaims}.${base64Url(new Uint8Array(signature))}`
  const response = await fetch(account.token_uri ?? "https://oauth2.googleapis.com/token", { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer", assertion }) })
  const payload = await response.json() as { access_token?: string }
  if (!response.ok || !payload.access_token) throw new Error("FCM OAuth token request failed")
  return payload.access_token
}

export async function sendIncidentFcm(registrationToken: string, incidentId: string): Promise<string> {
  return sendFcm(registrationToken, { incidentId, deepLink: `scut://incident/${incidentId}` })
}

export async function sendNeutralFcm(registrationToken: string, commandId: string): Promise<string> {
  return sendFcm(registrationToken, {
    kind: "NEUTRAL_TEST", commandId,
    title: "SCUT подключён",
    body: "Активного звонка сейчас нет. Связь между устройствами работает.",
  })
}

async function sendFcm(registrationToken: string, data: Record<string, string>): Promise<string> {
  const account = JSON.parse(configured("FCM_SERVICE_ACCOUNT_JSON")) as ServiceAccount
  if (!account.client_email || !account.private_key || !account.project_id) throw new Error("FCM service account is incomplete")
  const response = await fetch(`https://fcm.googleapis.com/v1/projects/${encodeURIComponent(account.project_id)}/messages:send`, {
    method: "POST",
    headers: { authorization: `Bearer ${await accessToken(account)}`, "content-type": "application/json" },
    body: JSON.stringify({ message: {
      token: registrationToken,
      // Data-only delivery lets the Android receiver open exactly the incident
      // supplied by Windows instead of an OS-generated generic notification.
      data,
      android: { priority: "high" },
    } }),
  })
  const payload = await response.json() as { name?: string; error?: { status?: string; message?: string } }
  if (!response.ok || !payload.name) {
    const code = payload.error?.status ?? "UNKNOWN"
    const message = (payload.error?.message ?? "FCM response did not contain a message name").slice(0, 240)
    throw new Error(`FCM_SEND_REJECTED status=${response.status} code=${code} message=${message}`)
  }
  return payload.name
}
