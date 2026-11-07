import { useState } from "react"
import { reportContent, sendFeedback, type ReportReason } from "../api"

const REASONS = ["Output missing", "Wrong output", "Code is wrong", "Formatting", "My details are wrong", "Too slow"]

function Thumb({ down }: { down?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" style={down ? { transform: "rotate(180deg)" } : undefined}>
      <path
        d="M7 10v11H3V10h4Zm2 11h8.3a2 2 0 0 0 2-1.6l1.4-7A2 2 0 0 0 18.7 10H14l.8-4.2a1.6 1.6 0 0 0-2.9-1.2L9 9.5V21Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** "Was this report right?" A thumbs down asks what went wrong. */
export function Feedback({ jobId }: { jobId: string }) {
  const [rating, setRating] = useState<"up" | "down" | null>(null)
  const [reasons, setReasons] = useState<string[]>([])
  const [comment, setComment] = useState("")
  const [sent, setSent] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState("")

  async function send(r: "up" | "down", why: string[] = [], text = "") {
    setSending(true)
    setError("")
    try {
      await sendFeedback(jobId, { rating: r, reasons: why, comment: text })
      setSent(true)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSending(false)
    }
  }

  if (sent) {
    return (
      <>
        <p className="feedback feedback--done" role="status">
          {rating === "up" ? "Thanks! Glad it worked." : "Thanks for telling us. We'll look into it."}
        </p>
        <ReportContent jobId={jobId} />
      </>
    )
  }

  return (
    <div className="feedback">
      <div className="feedback__ask">
        <span>Was this report right?</span>
        <button type="button" className={`feedback__thumb${rating === "up" ? " is-on" : ""}`} aria-label="Yes, it was right"
          aria-pressed={rating === "up"} disabled={sending}
          onClick={() => {
            setRating("up")
            void send("up")
          }}>
          <Thumb />
        </button>
        <button type="button" className={`feedback__thumb${rating === "down" ? " is-on" : ""}`} aria-label="No, something was wrong"
          aria-pressed={rating === "down"} disabled={sending} onClick={() => setRating("down")}>
          <Thumb down />
        </button>
      </div>
      {rating === "down" && (
        <form className="feedback__why" onSubmit={(e) => {
          e.preventDefault()
          void send("down", reasons, comment.trim())
        }}>
          <fieldset>
            <legend>What went wrong?</legend>
            <div className="feedback__chips">
              {REASONS.map((r) => (
                <label key={r} className={`chip${reasons.includes(r) ? " is-on" : ""}`}>
                  <input type="checkbox" checked={reasons.includes(r)}
                    onChange={(e) => setReasons((rs) => (e.target.checked ? [...rs, r] : rs.filter((x) => x !== r)))} />
                  {r}
                </label>
              ))}
            </div>
          </fieldset>
          <label className="field">
            <span>Tell us more (optional)</span>
            <textarea rows={3} maxLength={1000} value={comment} placeholder="Which task, and what did you expect?"
              onChange={(e) => setComment(e.target.value)} />
          </label>
          <button className="btn btn--secondary" type="submit" disabled={sending || (!reasons.length && !comment.trim())}>
            {sending ? "Sending…" : "Send"}
          </button>
        </form>
      )}
      {error && <p className="alert" role="alert">{error}</p>}
      <ReportContent jobId={jobId} />
    </div>
  )
}

const REPORT_REASONS: { id: ReportReason; label: string }[] = [
  { id: "offensive", label: "Offensive or inappropriate" },
  { id: "unsafe", label: "Harmful or unsafe code" },
  { id: "wrong", label: "Wrong or misleading" },
  { id: "copyright", label: "Copies someone else's work" },
  { id: "other", label: "Something else" },
]

/** Flag AI-written content for the site owner to review (required for AI apps on Google Play). */
export function ReportContent({ jobId }: { jobId: string }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState<ReportReason>("offensive")
  const [comment, setComment] = useState("")
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle")
  const [error, setError] = useState("")

  if (state === "sent") return <p className="hint" role="status">Reported. Thank you, we'll review it.</p>
  if (!open) {
    return (
      <button type="button" className="link link--muted feedback__report" onClick={() => setOpen(true)}>
        Report a problem with this content
      </button>
    )
  }
  return (
    <form className="feedback__why" onSubmit={async (e) => {
      e.preventDefault()
      setState("sending")
      setError("")
      try {
        await reportContent(jobId, { reason, comment: comment.trim(), task: null })
        setState("sent")
      } catch (err) {
        setError((err as Error).message)
        setState("idle")
      }
    }}>
      <label className="field">
        <span>What's the problem?</span>
        <select value={reason} onChange={(e) => setReason(e.target.value as ReportReason)}>
          {REPORT_REASONS.map((r) => (
            <option key={r.id} value={r.id}>{r.label}</option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Details (optional)</span>
        <textarea rows={2} maxLength={1000} value={comment} onChange={(e) => setComment(e.target.value)} />
      </label>
      <div className="row">
        <button className="btn btn--secondary" type="submit" disabled={state === "sending"}>
          {state === "sending" ? "Sending…" : "Send report"}
        </button>
        <button type="button" className="link link--muted" onClick={() => setOpen(false)}>Cancel</button>
      </div>
      {error && <p className="alert" role="alert">{error}</p>}
    </form>
  )
}
