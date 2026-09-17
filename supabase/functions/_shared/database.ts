import { configured } from "./http.ts"
import { sha256 } from "./security.ts"

export type Device = { id: string; role: "CONTROLLER" | "RECEIVER"; enabled: boolean; revoked_at: string | null }

function restUrl(path: string): string {
  return `${configured("SUPABASE_URL").replace(/\/$/, "")}/rest/v1/${path}`
}

export async function rest(path: string, init: RequestInit = {}): Promise<unknown> {
  const key = configured("SUPABASE_SERVICE_ROLE_KEY")
  const response = await fetch(restUrl(path), {
    ...init,
    headers: { apikey: key, authorization: `Bearer ${key}`, "content-type": "application/json", prefer: "return=representation", ...init.headers },
  })
  const text = await response.text()
  if (!response.ok) throw new Error(`PostgREST ${response.status}: ${text.slice(0, 160)}`)
  return text ? JSON.parse(text) : null
}

export async function rpc(name: string, value: Record<string, unknown>): Promise<unknown> {
  return rest(`rpc/${name}`, { method: "POST", body: JSON.stringify(value) })
}

export async function deviceForRequest(request: Request): Promise<Device | null> {
  const credential = request.headers.get("x-scut-device-token")
  if (!credential || credential.length > 200) return null
  const result = await rest(`devices?credential_hash=eq.${await sha256(credential)}&revoked_at=is.null&select=id,role,enabled,revoked_at`)
  return Array.isArray(result) && result.length === 1 ? result[0] as Device : null
}

export async function touchDevice(id: string, patch: Record<string, unknown> = {}): Promise<void> {
  await rest(`devices?id=eq.${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ ...patch, last_seen_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
  })
}
