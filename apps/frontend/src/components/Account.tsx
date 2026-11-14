import { useState } from "react"
import { adClaim, adTicket, requestCode, signOut, verifyCode } from "../api"
import { rewardedConfigured, showRewardedAd } from "../rewarded"
import type { Me, Meta } from "../types"

/** "3 of 3 free reports left today", plus any extra credits. */
export function creditsLine(me: Me): string {
  const c = me.credits
  if (!c) return ""
  const when = c.period === "day" ? "today" : "this month"
  const free = `${c.free} of ${c.free_total} free ${c.free_total === 1 ? "report" : "reports"} left ${when}`
  return c.extra > 0 ? `${free}, plus ${c.extra} extra` : free
}

/** Sign in with a code sent to the student's college email. No password. */
export function Account({ auth, me, onChange }: {
  auth: Meta["auth"]
  me: Me | null
  onChange: (me: Me) => void
}) {
  const [email, setEmail] = useState("")
  const [code, setCode] = useState("")
  const [sentTo, setSentTo] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const domains = auth.domains.filter((d) => d !== "*")
  const example = domains.length ? `yourUID@${domains[0]}` : "you@example.com"

  async function run(work: () => Promise<void>) {
    setBusy(true)
    setError("")
    try {
      await work()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const send = () =>
    run(async () => {
      const address = email.trim().toLowerCase()
      await requestCode(address)
      setSentTo(address)
      setCode("")
    })

  /** A ticket, the ad, then the claim. The report is added only when the ad was watched to the end. */
  const watchAd = () =>
    run(async () => {
      const started = Date.now()
      const offer = await adTicket()
      const result = await showRewardedAd(offer.min_seconds)
      if (result === "unavailable") throw new Error("No ad is available right now. Try again in a little while.")
      if (result === "closed") throw new Error("The ad was closed before it finished, so no report was added.")
      const early = offer.min_seconds * 1000 - (Date.now() - started)
      if (early > 0) await new Promise((r) => setTimeout(r, early))
      onChange(await adClaim(offer.ticket))
    })

  if (me?.user) {
    const ads = me.ads?.enabled && rewardedConfigured() ? me.ads : null
    return (
      <section className="account account--in" aria-label="Your account">
        <p className="account__who">
          Signed in as <b>{me.user.email}</b>
        </p>
        <p className="hint">{creditsLine(me)}.</p>
        {ads && (
          <div className="account__ad">
            <button type="button" className="btn btn--secondary btn--wide" disabled={busy || ads.left <= 0}
              onClick={() => void watchAd()}>
              {busy
                ? "One moment…"
                : ads.left > 0
                  ? `Watch an ad for ${ads.reward === 1 ? "1 more report" : `${ads.reward} more reports`}`
                  : "No more ad reports today"}
            </button>
            <p className="hint">
              {ads.left} of {ads.per_day} left today. The report is added when the ad ends.
            </p>
          </div>
        )}
        <button type="button" className="link link--muted" disabled={busy}
          onClick={() => run(async () => {
            await signOut()
            onChange({ user: null })
          })}>
          Sign out
        </button>
        {error && <p className="alert" role="alert">{error}</p>}
      </section>
    )
  }

  return (
    <section className="account" aria-labelledby="account-title">
      <h2 id="account-title">Sign in to write a report</h2>
      {sentTo ? (
        <form onSubmit={(e) => {
          e.preventDefault()
          void run(async () => onChange(await verifyCode(sentTo, code)))
        }}>
          <p className="hint">
            We sent a 6-digit code to <b>{sentTo}</b>. It can take a minute; check your spam folder too.
          </p>
          <label className="field">
            <span>Code from the email</span>
            <input value={code} inputMode="numeric" autoComplete="one-time-code" maxLength={8} autoFocus
              placeholder="123456" onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
          </label>
          <button type="submit" className="btn btn--primary btn--wide" disabled={busy || code.length < 6}>
            {busy ? "Checking…" : "Sign in"}
          </button>
          <div className="row row--between">
            <button type="button" className="link link--muted" disabled={busy} onClick={() => void send()}>
              Send a new code
            </button>
            <button type="button" className="link link--muted" onClick={() => {
              setSentTo("")
              setError("")
            }}>
              Use another email
            </button>
          </div>
        </form>
      ) : (
        <form onSubmit={(e) => {
          e.preventDefault()
          void send()
        }}>
          <p className="hint">
            {domains.length
              ? `Use your college email (${domains.map((d) => "@" + d).join(" or ")}). `
              : ""}
            We'll email you a code. No password. You get {auth.free} free{" "}
            {auth.free === 1 ? "report" : "reports"} a {auth.period}.
          </p>
          <label className="field">
            <span>College email</span>
            <input type="email" value={email} autoComplete="email" placeholder={example}
              onChange={(e) => setEmail(e.target.value)} />
          </label>
          <button type="submit" className="btn btn--primary btn--wide" disabled={busy || !email.includes("@")}>
            {busy ? "Sending…" : "Email me a code"}
          </button>
        </form>
      )}
      {error && <p className="alert" role="alert">{error}</p>}
    </section>
  )
}
