import type { Draft, DraftEvent, Explanation, Meta, RenderResult, Task } from "./types"

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

/**
 * An anonymous id this browser keeps, so limits are counted per student instead of per Wi-Fi
 * network (a whole college can share one IP address). It identifies nobody.
 */
function clientId(): string {
  const KEY = "lf.client"
  try {
    const known = localStorage.getItem(KEY)
    if (known && /^[A-Za-z0-9_-]{16,64}$/.test(known)) return known
  } catch {
    /* storage blocked: a fresh id per visit still works */
  }
  const bytes = new Uint8Array(18)
  crypto.getRandomValues(bytes)
  const id = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")
  try {
    localStorage.setItem(KEY, id)
  } catch {
    /* ignore */
  }
  return id
}

const CLIENT = clientId()

function withClient(init: RequestInit = {}): RequestInit {
  const headers = new Headers(init.headers)
  headers.set("X-Client-Id", CLIENT)
  return { ...init, headers }
}

const call = (url: string, init?: RequestInit) => fetch(url, withClient(init))

async function fail(res: Response): Promise<never> {
  let message = `The server answered ${res.status}.`
  try {
    const body = await res.json()
    if (typeof body.detail === "string") message = body.detail
  } catch {
    /* not JSON */
  }
  throw new ApiError(message, res.status)
}

async function json<T>(res: Promise<Response>): Promise<T> {
  let r: Response
  try {
    r = await res
  } catch {
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0)
  }
  if (!r.ok) await fail(r)
  return r.json() as Promise<T>
}

/**
 * The server sleeps when nobody has used it for a while and takes up to a minute to wake.
 * `onSlow` is called once if the first answer takes more than a few seconds, so the page can say so.
 */
export async function getMeta(onSlow?: () => void): Promise<Meta> {
  const slow = setTimeout(() => onSlow?.(), 3500)
  const deadline = Date.now() + 120_000
  try {
    for (let attempt = 0; ; attempt++) {
      try {
        const res = await call("/api/meta")
        if (res.ok) return (await res.json()) as Meta
        // 502/503/504 while the host starts the app: keep waiting
        if (![502, 503, 504].includes(res.status) || Date.now() > deadline) await fail(res)
      } catch (e) {
        if (e instanceof ApiError) throw e
        if (Date.now() > deadline) throw new ApiError("Can't reach the server. Check your connection and try again.", 0)
      }
      onSlow?.()
      await new Promise((r) => setTimeout(r, Math.min(2000 + attempt * 1000, 6000)))
    }
  } finally {
    clearTimeout(slow)
  }
}

async function readEvents(res: Response, onEvent: (e: DraftEvent) => void): Promise<void> {
  if (!res.ok || !res.body) await fail(res)
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let nl: number
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim()
      buffer = buffer.slice(nl + 1)
      if (line) onEvent(JSON.parse(line) as DraftEvent)
    }
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as DraftEvent)
}

export async function createDraft(
  form: FormData,
  onEvent: (e: DraftEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await call("/api/drafts", { method: "POST", body: form, signal })
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0)
  }
  await readEvents(res, onEvent)
}

/** Everything that happened to a report after event `after`: used when the connection dropped. */
export async function resumeDraft(
  job: string,
  after: number,
  onEvent: (e: DraftEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await call(`/api/jobs/${job}/events?after=${after}`, { signal })
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0)
  }
  await readEvents(res, onEvent)
}

export const cancelJob = (job: string) =>
  call(`/api/jobs/${job}/cancel`, { method: "POST" }).catch(() => undefined)

export const deleteJob = (job: string) => json<{ ok: boolean }>(call(`/api/jobs/${job}`, { method: "DELETE" }))

export const runTask = (job: string, index: number, task: Task) =>
  json<Task>(
    call(`/api/jobs/${job}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index, task }),
    }),
  )

export const explainTask = (job: string, index: number, task: Task) =>
  json<Explanation>(
    call(`/api/jobs/${job}/explain`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index, task }),
    }),
  )

export function uploadImage(job: string, file: File) {
  const form = new FormData()
  form.append("file", file)
  return json<{ name: string }>(call(`/api/jobs/${job}/images`, { method: "POST", body: form }))
}

export const renderReport = (
  job: string,
  body: { draft: Draft; fields: { label: string; value: string }[]; template: string; pdf: boolean; sign_code: boolean },
) =>
  json<RenderResult>(
    call(`/api/jobs/${job}/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  )

export const sendFeedback = (job: string, body: { rating: "up" | "down"; reasons: string[]; comment: string }) =>
  json<{ ok: boolean }>(
    call(`/api/jobs/${job}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  )

export type ReportReason = "offensive" | "unsafe" | "wrong" | "copyright" | "other"

export const reportContent = (job: string, body: { reason: ReportReason; comment: string; task: number | null }) =>
  json<{ ok: boolean }>(
    call(`/api/jobs/${job}/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  )

export const fileUrl = (job: string, name: string, render?: string) =>
  render ? `/api/jobs/${job}/files/${render}/${encodeURIComponent(name)}` : `/api/jobs/${job}/files/${encodeURIComponent(name)}`
