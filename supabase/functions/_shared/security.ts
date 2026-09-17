import { configured } from "./http.ts"

const encoder = new TextEncoder()

export async function sha256(value: string): Promise<string> {
  const bytes = new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(value)))
  return Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("")
}

export function newCredential(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32))
  let binary = ""
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "")
}

export function matchesSecret(actual: string, expected: string): boolean {
  const left = encoder.encode(actual)
  const right = encoder.encode(expected)
  let difference = left.length ^ right.length
  const length = Math.max(left.length, right.length)
  for (let index = 0; index < length; index++) difference |= (left[index] ?? 0) ^ (right[index] ?? 0)
  return difference === 0
}

export async function masterPasswordAccepted(password: string): Promise<boolean> {
  // The deployed secret is the SHA-256 verifier generated out of band; the
  // password itself never becomes an APK, migration, log entry, or response.
  return matchesSecret(await sha256(password), configured("SCUT_MASTER_PASSWORD_SHA256"))
}

export function exeAuthenticated(request: Request): boolean {
  return matchesSecret(request.headers.get("x-scut-exe-token") ?? "", configured("SCUT_EXE_CONTROL_TOKEN"))
}
