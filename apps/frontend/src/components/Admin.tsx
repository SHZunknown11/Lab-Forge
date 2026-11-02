import { useCallback, useEffect, useMemo, useState } from "react"

/** Private activity panel at /admin: who made which report and whether its programs ran. */

interface LogTask {
  title: string
  language: string
  status: string
  note: string
  output: string
}

interface Report {
  job: string
  ts: string
  updated: string
  name: string
  uid: string
  ip: string
  title: string
  subject: string
  language: string
  cached: boolean
  error: string
  tasks: LogTask[]
  seconds: number | null
  sheet: string
  downloads: number
  warnings: string[]
  reruns: number
  issue: boolean
  feedback: { rating: "up" | "down"; reasons: string[]; comment: string; ts: string } | null
}

const TOKEN_KEY = "lf.admin"

function readToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? ""
  } catch {
    return ""
  }
}

function ago(ts: string) {
  const s = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000)
  if (s < 60) return "just now"
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

const STATUS_LABEL: Record<string, string> = { passed: "Ran", failed: "Failed", not_run: "Not run" }

export default function Admin() {
  const [token, setToken] = useState(readToken)
  const [draftToken, setDraftToken] = useState("")
  const [days, setDays] = useState(7)
  const [reports, setReports] = useState<Report[] | null>(null)
  const [storage, setStorage] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState("")
  const [issuesOnly, setIssuesOnly] = useState(false)
  const [vote, setVote] = useState<"" | "up" | "down" | "any">("")
  const [open, setOpen] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError("")
    try {
      const r = await fetch(`/api/admin/activity?days=${days}`, { headers: { "X-Admin-Token": token } })
      if (r.status === 404) {
        setToken("")
        setError("That key didn't work.")
        try {
          localStorage.removeItem(TOKEN_KEY)
        } catch {
          /* private window */
        }
        return
      }
      if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? `Error ${r.status}`)
      const data = await r.json()
      setReports(data.reports)
      setStorage(data.storage)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [token, days])

  useEffect(() => {
    void load()
  }, [load])

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (reports ?? []).filter(
      (r) =>
        (!issuesOnly || r.issue) &&
        (!vote || (vote === "any" ? !!r.feedback : r.feedback?.rating === vote)) &&
        (!q || [r.name, r.uid, r.title, r.subject, r.ip, r.job].some((v) => v.toLowerCase().includes(q))),
    )
  }, [reports, query, issuesOnly, vote])

  if (!token) {
    return (
      <main className="admin admin--gate">
        <form
          className="admin__gate"
          onSubmit={(e) => {
            e.preventDefault()
            const t = draftToken.trim()
            if (!t) return
            try {
              localStorage.setItem(TOKEN_KEY, t)
            } catch {
              /* private window: keep it for this visit only */
            }
            setToken(t)
          }}
        >
          <h1>Activity</h1>
          <p className="hint">Enter the admin key (LABFORGE_ADMIN_TOKEN).</p>
          <input
            type="password"
            autoFocus
            autoComplete="current-password"
            value={draftToken}
            onChange={(e) => setDraftToken(e.target.value)}
            aria-label="Admin key"
          />
          {error && <p className="alert">{error}</p>}
          <button className="btn btn--primary" type="submit">
            Open
          </button>
        </form>
      </main>
    )
  }

  const total = reports?.length ?? 0
  const issues = reports?.filter((r) => r.issue).length ?? 0
  const downloaded = reports?.filter((r) => r.downloads > 0).length ?? 0
  const ups = reports?.filter((r) => r.feedback?.rating === "up").length ?? 0
  const downs = reports?.filter((r) => r.feedback?.rating === "down").length ?? 0

  return (
    <main className="admin">
      <header className="admin__head">
        <h1>Activity</h1>
        <span className="admin__storage" title="Where the log is kept">
          {storage === "postgres" ? "Database" : storage === "file" ? "Server file (wiped on redeploy)" : ""}
        </span>
        <button className="btn btn--quiet" onClick={() => void load()} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </header>

      <div className="admin__bar">
        <input
          type="search"
          placeholder="Search name, UID, experiment, IP"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search"
        />
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Period">
          <option value={1}>Today</option>
          <option value={7}>7 days</option>
          <option value={30}>30 days</option>
        </select>
        <select value={vote} onChange={(e) => setVote(e.target.value as typeof vote)} aria-label="Feedback">
          <option value="">All feedback</option>
          <option value="down">Thumbs down</option>
          <option value="up">Thumbs up</option>
          <option value="any">Any feedback</option>
        </select>
        <label className="check">
          <input type="checkbox" checked={issuesOnly} onChange={(e) => setIssuesOnly(e.target.checked)} />
          Issues only
        </label>
      </div>

      {error && <p className="alert">{error}</p>}

      {reports && (
        <p className="admin__stats">
          <b>{total}</b> reports · <b className={issues ? "admin__bad" : ""}>{issues}</b> with issues ·{" "}
          <b>{downloaded}</b> downloaded · <b>{ups}</b> 👍 · <b className={downs ? "admin__bad" : ""}>{downs}</b> 👎
        </p>
      )}

      <ul className="admin__list">
        {shown.map((r) => {
          const isOpen = open === r.job
          return (
            <li key={r.job} className={`admin__item${r.issue ? " admin__item--issue" : ""}`}>
              <button className="admin__row" onClick={() => setOpen(isOpen ? null : r.job)} aria-expanded={isOpen}>
                <span className="admin__when" title={new Date(r.ts).toLocaleString()}>
                  {ago(r.ts)}
                </span>
                <span className="admin__who">
                  {r.name || <i>Unknown</i>}
                  {r.uid && <small>{r.uid}</small>}
                </span>
                <span className="admin__what">
                  {r.title || "Untitled"}
                  {r.subject && <small>{r.subject}</small>}
                </span>
                <span className="admin__dots" aria-label={r.tasks.map((t) => `${t.title}: ${STATUS_LABEL[t.status] ?? t.status}`).join(", ")}>
                  {r.tasks.map((t, i) => (
                    <i key={i} className={`admin__dot admin__dot--${t.status}`} title={`${t.title}: ${STATUS_LABEL[t.status] ?? t.status}`} />
                  ))}
                  {r.error && <i className="admin__dot admin__dot--failed" title={r.error} />}
                  {r.feedback && (
                    <span className={`admin__vote admin__vote--${r.feedback.rating}`}
                      title={r.feedback.rating === "up" ? "Thumbs up" : `Thumbs down: ${[...r.feedback.reasons, r.feedback.comment].filter(Boolean).join(". ")}`}>
                      {r.feedback.rating === "up" ? "👍" : "👎"}
                    </span>
                  )}
                </span>
                <span className={`admin__pill${r.issue ? " admin__pill--issue" : ""}`}>{r.issue ? "Issue" : "OK"}</span>
              </button>

              {isOpen && (
                <div className="admin__detail">
                  {r.error && <p className="alert">{r.error}</p>}
                  {r.feedback && (
                    <div className={`admin__feedback admin__feedback--${r.feedback.rating}`}>
                      <b>{r.feedback.rating === "up" ? "👍 The student said it was right" : "👎 The student said something was wrong"}</b>
                      {r.feedback.reasons?.length > 0 && <p>{r.feedback.reasons.join(" · ")}</p>}
                      {r.feedback.comment && <p>“{r.feedback.comment}”</p>}
                    </div>
                  )}
                  {r.tasks.map((t, i) => (
                    <div key={i} className={`admin__task admin__task--${t.status}`}>
                      <div className="admin__taskhead">
                        <b>{t.title || `Task ${i + 1}`}</b>
                        <span>{t.language}</span>
                        <span>{STATUS_LABEL[t.status] ?? t.status}</span>
                      </div>
                      {t.note && <p>{t.note}</p>}
                      {t.output && <pre>{t.output}</pre>}
                    </div>
                  ))}
                  {r.warnings.length > 0 && <p className="hint">Download warnings: {r.warnings.join(" ")}</p>}
                  <dl className="admin__meta">
                    <dt>IP</dt>
                    <dd>{r.ip || "—"}</dd>
                    <dt>Time</dt>
                    <dd>{new Date(r.ts).toLocaleString()}</dd>
                    <dt>Took</dt>
                    <dd>{r.seconds == null ? "—" : `${r.seconds}s`}{r.cached ? " (cached sheet)" : ""}</dd>
                    <dt>Downloads</dt>
                    <dd>{r.downloads}</dd>
                    <dt>Re-runs</dt>
                    <dd>{r.reruns}</dd>
                    <dt>Job</dt>
                    <dd className="mono">{r.job}</dd>
                  </dl>
                  {r.sheet && (
                    <details>
                      <summary>Sheet text</summary>
                      <pre>{r.sheet}</pre>
                    </details>
                  )}
                </div>
              )}
            </li>
          )
        })}
      </ul>
      {reports && shown.length === 0 && <p className="hint admin__empty">Nothing here yet.</p>}
    </main>
  )
}
