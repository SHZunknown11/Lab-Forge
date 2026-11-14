import { useCallback, useEffect, useState } from "react"

/** The owner's view of sessions that went wrong (with the code that failed) and of accounts. */

interface FlagRow {
  id: string
  ts: number
  email: string
  job: string
  kind: "draft" | "run"
  reason: string
}

interface FlagTask {
  title: string
  language: string
  status: string
  note: string
  stdin: string
  output: string
  problem: string
  edited: boolean
  files: { name: string; code: string }[]
}

interface FlagDetail extends FlagRow {
  sheet?: string
  subject?: string
  language?: string
  title?: string
  error?: string
  ip?: string
  cached?: boolean
  tasks: FlagTask[]
}

interface UserRow {
  email: string
  created: number
  last_login: number
  ip: string
  blocked: boolean
  reports: number
  credits: { free: number; free_total: number; extra: number; left: number }
}

async function ask<T>(token: string, url: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(url, {
    ...init,
    headers: { "X-Admin-Token": token, ...(init.body ? { "Content-Type": "application/json" } : {}) },
  })
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? `Error ${r.status}`)
  return r.json() as Promise<T>
}

const when = (ts: number) => new Date(ts * 1000).toLocaleString()

export function Flags({ token }: { token: string }) {
  const [rows, setRows] = useState<FlagRow[] | null>(null)
  const [keep, setKeep] = useState(30)
  const [open, setOpen] = useState<FlagDetail | null>(null)
  const [query, setQuery] = useState("")
  const [error, setError] = useState("")

  const load = useCallback(() => {
    setError("")
    ask<{ flags: FlagRow[]; keep_days: number }>(token, "/api/admin/flags?days=90")
      .then((d) => {
        setRows(d.flags)
        setKeep(d.keep_days)
      })
      .catch((e: Error) => setError(e.message))
  }, [token])
  useEffect(load, [load])

  const show = (row: FlagRow) => {
    if (open?.id === row.id) return setOpen(null)
    ask<FlagDetail>(token, `/api/admin/flags/${encodeURIComponent(row.id)}`)
      .then(setOpen)
      .catch((e: Error) => setError(e.message))
  }

  const remove = (row: FlagRow) => {
    if (!window.confirm("Delete this saved session?")) return
    ask(token, `/api/admin/flags/${encodeURIComponent(row.id)}`, { method: "DELETE" })
      .then(() => {
        setOpen(null)
        setRows((list) => (list ?? []).filter((x) => x.id !== row.id))
      })
      .catch((e: Error) => setError(e.message))
  }

  const q = query.trim().toLowerCase()
  const shown = (rows ?? []).filter((r) => !q || [r.email, r.reason, r.job].some((v) => v.toLowerCase().includes(q)))

  return (
    <>
      <div className="admin__bar">
        <input type="search" placeholder="Search email, language, error" value={query} aria-label="Search"
          onChange={(e) => setQuery(e.target.value)} />
        <button className="btn btn--quiet" onClick={load}>Refresh</button>
      </div>
      <p className="admin__stats">
        <b>{rows?.length ?? 0}</b> sessions with a problem. Each is kept for {keep} days.
      </p>
      {error && <p className="alert">{error}</p>}
      <ul className="admin__list">
        {shown.map((r) => (
          <li key={r.id} className="admin__item admin__item--issue">
            <button className="admin__row" onClick={() => show(r)} aria-expanded={open?.id === r.id}>
              <span className="admin__when" title={when(r.ts)}>{new Date(r.ts * 1000).toLocaleDateString()}</span>
              <span className="admin__who">{r.email || <i>Not signed in</i>}</span>
              <span className="admin__what">
                {r.reason}
                <small>{r.kind === "run" ? "Run again by the student" : "While writing the report"}</small>
              </span>
            </button>
            {open?.id === r.id && (
              <div className="admin__detail">
                {open.error && <p className="alert">{open.error}</p>}
                {open.tasks.map((t, i) => (
                  <div key={i} className={`admin__task admin__task--${t.status}`}>
                    <div className="admin__taskhead">
                      <b>{t.title || `Task ${i + 1}`}</b>
                      <span>{t.language}</span>
                      <span>{t.status}{t.edited ? " (student's own code)" : ""}</span>
                    </div>
                    {t.note && <p>{t.note}</p>}
                    {t.problem && (
                      <details>
                        <summary>Problem</summary>
                        <pre>{t.problem}</pre>
                      </details>
                    )}
                    {t.files.map((f) => (
                      <details key={f.name} open={t.status !== "passed"}>
                        <summary>{f.name}</summary>
                        <pre className="admin__code">{f.code}</pre>
                      </details>
                    ))}
                    {t.stdin && (
                      <details>
                        <summary>Input</summary>
                        <pre>{t.stdin}</pre>
                      </details>
                    )}
                    {t.output && <pre className="admin__code">{t.output}</pre>}
                  </div>
                ))}
                <dl className="admin__meta">
                  <dt>Email</dt>
                  <dd>{open.email || "—"}</dd>
                  <dt>Time</dt>
                  <dd>{when(open.ts)}</dd>
                  <dt>Subject</dt>
                  <dd>{open.subject || "—"}</dd>
                  <dt>IP</dt>
                  <dd>{open.ip || "—"}</dd>
                  <dt>Job</dt>
                  <dd className="mono">{open.job}</dd>
                </dl>
                {open.sheet && (
                  <details>
                    <summary>Sheet text</summary>
                    <pre className="admin__code">{open.sheet}</pre>
                  </details>
                )}
                <button className="btn btn--quiet" onClick={() => remove(r)}>Delete this saved session</button>
              </div>
            )}
          </li>
        ))}
      </ul>
      {rows && shown.length === 0 && <p className="hint admin__empty">Nothing here yet.</p>}
    </>
  )
}

export function Users({ token }: { token: string }) {
  const [rows, setRows] = useState<UserRow[] | null>(null)
  const [query, setQuery] = useState("")
  const [error, setError] = useState("")

  const load = useCallback(() => {
    setError("")
    ask<{ users: UserRow[] }>(token, "/api/admin/users")
      .then((d) => setRows(d.users))
      .catch((e: Error) => setError(e.message))
  }, [token])
  useEffect(load, [load])

  const act = (url: string, body: unknown) =>
    ask(token, url, { method: "POST", body: JSON.stringify(body) })
      .then(load)
      .catch((e: Error) => setError(e.message))

  const grant = (u: UserRow) => {
    const typed = window.prompt(`Extra reports for ${u.email} (a negative number takes them back):`, "5")
    const amount = Number(typed)
    if (typed === null || !Number.isInteger(amount) || amount === 0) return
    void act("/api/admin/credits", { email: u.email, amount })
  }

  const q = query.trim().toLowerCase()
  const shown = (rows ?? []).filter((u) => !q || u.email.includes(q))

  return (
    <>
      <div className="admin__bar">
        <input type="search" placeholder="Search email" value={query} aria-label="Search"
          onChange={(e) => setQuery(e.target.value)} />
        <button className="btn btn--quiet" onClick={load}>Refresh</button>
      </div>
      <p className="admin__stats">
        <b>{rows?.length ?? 0}</b> accounts · <b>{rows?.reduce((n, u) => n + u.reports, 0) ?? 0}</b> reports written
      </p>
      {error && <p className="alert">{error}</p>}
      <table className="admin__users">
        <thead>
          <tr>
            <th>Email</th>
            <th>Reports</th>
            <th>Left</th>
            <th>Last sign-in</th>
            <th>IP code</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {shown.map((u) => (
            <tr key={u.email}>
              <td>{u.email}{u.blocked && <b className="admin__bad"> (blocked)</b>}</td>
              <td>{u.reports}</td>
              <td>{u.credits.free} free{u.credits.extra ? ` + ${u.credits.extra}` : ""}</td>
              <td>{when(u.last_login)}</td>
              <td className="mono">{u.ip || "—"}</td>
              <td>
                <button className="link" onClick={() => grant(u)}>Give reports</button>{" "}
                <button className="link link--muted"
                  onClick={() => void act("/api/admin/block", { email: u.email, blocked: !u.blocked })}>
                  {u.blocked ? "Unblock" : "Block"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows && shown.length === 0 && <p className="hint admin__empty">Nobody has signed in yet.</p>}
    </>
  )
}
