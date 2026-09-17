export const corsHeaders = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "content-type, x-scut-device-token, x-scut-exe-token",
  "access-control-allow-methods": "POST, OPTIONS",
}

export function json(status: number, body: Record<string, unknown>): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  })
}

export async function bodyObject(request: Request): Promise<Record<string, unknown> | null> {
  const length = Number(request.headers.get("content-length") ?? "0")
  if (length > 16_384) return null
  try {
    const value = await request.json()
    return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null
  } catch {
    return null
  }
}

export function requiredString(body: Record<string, unknown>, name: string, maxLength: number): string | null {
  const value = body[name]
  if (typeof value !== "string") return null
  const normalized = value.trim()
  return normalized.length > 0 && normalized.length <= maxLength ? normalized : null
}

export function configured(name: string): string {
  const value = Deno.env.get(name)?.trim()
  if (!value) throw new Error(`Missing ${name}`)
  return value
}

export function unsupported(error: unknown): Response {
  console.error(error instanceof Error ? error.message : "unexpected function error")
  return json(503, { error: { code: "CONTROL_PLANE_UNAVAILABLE", message: "SCUT control plane is not configured" } })
}
