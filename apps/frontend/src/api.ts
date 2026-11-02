import type { Draft, DraftEvent, Meta, RenderResult, Task } from "./types"

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

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

export const getMeta = () => json<Meta>(fetch("/api/meta"))

export async function createDraft(
  form: FormData,
  onEvent: (e: DraftEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await fetch("/api/drafts", { method: "POST", body: form, signal })
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0)
  }
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

export const runTask = (job: string, index: number, task: Task) =>
  json<Task>(
    fetch(`/api/jobs/${job}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index, task }),
    }),
  )

export function uploadImage(job: string, file: File) {
  const form = new FormData()
  form.append("file", file)
  return json<{ name: string }>(fetch(`/api/jobs/${job}/images`, { method: "POST", body: form }))
}

export const renderReport = (
  job: string,
  body: { draft: Draft; fields: { label: string; value: string }[]; template: string; pdf: boolean; sign_code: boolean },
) =>
  json<RenderResult>(
    fetch(`/api/jobs/${job}/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  )

export const sendFeedback = (job: string, body: { rating: "up" | "down"; reasons: string[]; comment: string }) =>
  json<{ ok: boolean }>(
    fetch(`/api/jobs/${job}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  )

export const fileUrl = (job: string, name: string, render?: string) =>
  render ? `/api/jobs/${job}/files/${render}/${encodeURIComponent(name)}` : `/api/jobs/${job}/files/${encodeURIComponent(name)}`
