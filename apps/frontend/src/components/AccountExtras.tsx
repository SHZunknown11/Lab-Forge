import { useState } from "react"
import { buyPack } from "../pay"
import { isNative, SITE_URL } from "../native"
import type { Me, Meta } from "../types"

const REF_KEY = "lf.ref"

/** The friend's code from an invite link (?ref=...), remembered until this browser signs up. */
export function rememberInvite() {
  try {
    const code = new URLSearchParams(location.search).get("ref")?.trim().toLowerCase() ?? ""
    if (/^[a-f0-9]{10}$/.test(code)) localStorage.setItem(REF_KEY, code)
  } catch {
    /* storage blocked: the invite just doesn't count */
  }
}

export function inviteCode(): string {
  try {
    return localStorage.getItem(REF_KEY) ?? ""
  } catch {
    return ""
  }
}

/** More reports for a signed-in student: buy a pack, or invite a classmate. */
export function AccountExtras({ me, pay, onChange }: { me: Me; pay: Meta["pay"]; onChange: (me: Me) => void }) {
  const [busy, setBusy] = useState("")
  const [error, setError] = useState("")
  const [copied, setCopied] = useState(false)
  const invite = me.referral?.enabled ? me.referral : null
  if (!me.user || (!pay.enabled && !invite)) return null

  const buy = async (id: string) => {
    setBusy(id)
    setError("")
    try {
      const paid = await buyPack(id)
      if (paid) onChange(paid)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy("")
    }
  }

  const link = invite ? `${(SITE_URL || location.origin)}/?ref=${invite.code}` : ""
  const pitch = invite
    ? `I make my lab reports with LabForge: it writes the code, runs it and gives you the Word and PDF file. ` +
      `Sign up with my link and you get ${invite.welcome === 1 ? "an extra report" : `${invite.welcome} extra reports`}: ${link}`
    : ""

  return (
    <section className="account account--more" aria-label="Get more reports">
      {pay.enabled && !isNative() && (
        <div className="account__block">
          <h2>Buy reports</h2>
          <div className="packs">
            {pay.packs.map((p) => (
              <button key={p.id} type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => void buy(p.id)}>
                {busy === p.id ? "Opening…" : `${p.reports} reports for ₹${p.price}`}
              </button>
            ))}
          </div>
          <p className="hint">Paid with UPI, card or net banking through Razorpay. Bought reports don't expire.</p>
        </div>
      )}
      {invite && (
        <div className="account__block">
          <h2>Invite a classmate</h2>
          <p className="hint">
            You get {invite.reward} {invite.reward === 1 ? "report" : "reports"} when a classmate signs up with your
            link and writes their first report.
            {invite.joined + invite.waiting > 0 &&
              ` So far: ${invite.joined} joined${invite.waiting ? `, ${invite.waiting} signed up but haven't written one yet` : ""}.`}
          </p>
          <div className="row">
            <a className="btn btn--secondary" href={`https://wa.me/?text=${encodeURIComponent(pitch)}`} target="_blank"
              rel="noopener noreferrer">
              Share on WhatsApp
            </a>
            <button type="button" className="link" onClick={() => {
              void navigator.clipboard?.writeText(link).then(() => {
                setCopied(true)
                setTimeout(() => setCopied(false), 2000)
              })
            }}>
              {copied ? "Copied" : "Copy my link"}
            </button>
          </div>
        </div>
      )}
      {error && <p className="alert" role="alert">{error}</p>}
    </section>
  )
}
