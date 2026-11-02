import { useState } from "react"
import { sendFeedback } from "../api"

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
      <p className="feedback feedback--done" role="status">
        {rating === "up" ? "Thanks! Glad it worked." : "Thanks for telling us. We'll look into it."}
      </p>
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
    </div>
  )
}
