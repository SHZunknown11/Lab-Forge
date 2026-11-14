/**
 * Rewarded ads: the student chooses to watch an ad and gets another report.
 *
 * Uses Google Ad Manager's rewarded format for the web (Google Publisher Tag), which is the
 * format made for "watch this to unlock that". Set VITE_REWARDED_AD_UNIT at build time to the
 * ad unit path from Ad Manager, e.g. /1234567/labforge_rewarded. Ordinary AdSense display
 * units must not be used for this: paying visitors to look at them is against AdSense policy.
 *
 * VITE_REWARDED_AD_TEST=1 shows a labelled stand-in with a countdown instead, for development.
 */

const UNIT = (import.meta.env.VITE_REWARDED_AD_UNIT as string | undefined)?.trim() || ""
const TEST = (import.meta.env.VITE_REWARDED_AD_TEST as string | undefined) === "1"
const READY_TIMEOUT_MS = 20_000

export type AdResult = "granted" | "closed" | "unavailable"

export const rewardedConfigured = () => !!UNIT || TEST

interface RewardedEvent {
  slot: unknown
  isEmpty?: boolean
  makeRewardedVisible?: () => void
}

interface PubAds {
  addEventListener: (name: string, fn: (e: RewardedEvent) => void) => void
  removeEventListener: (name: string, fn: (e: RewardedEvent) => void) => void
}

interface GoogleTag {
  cmd: (() => void)[]
  defineOutOfPageSlot: (unit: string, format: unknown) => { addService: (s: PubAds) => void } | null
  enums: { OutOfPageFormat: { REWARDED: unknown } }
  pubads: () => PubAds
  enableServices: () => void
  display: (slot: unknown) => void
  destroySlots: (slots: unknown[]) => void
}

declare global {
  interface Window {
    googletag?: GoogleTag
  }
}

let scriptAdded = false
function loadGpt(): GoogleTag {
  const tag = (window.googletag = window.googletag || ({ cmd: [] } as unknown as GoogleTag))
  if (!scriptAdded) {
    scriptAdded = true
    const s = document.createElement("script")
    s.async = true
    s.src = "https://securepubads.g.doubleclick.net/tag/js/gpt.js"
    s.crossOrigin = "anonymous"
    document.head.appendChild(s)
  }
  return tag
}

/** Show one rewarded ad. Resolves when it has been watched, closed early, or none could be shown. */
export function showRewardedAd(testSeconds = 15): Promise<AdResult> {
  if (!UNIT) return TEST ? standIn(testSeconds) : Promise.resolve("unavailable")
  return new Promise((resolve) => {
    const tag = loadGpt()
    let done = false
    let visible = false
    let granted = false
    let cleanup = () => {}
    const finish = (result: AdResult) => {
      if (done) return
      done = true
      clearTimeout(timer)
      cleanup()
      resolve(result)
    }
    // An ad blocker, no network or no ad to show: don't leave the student waiting.
    const timer = setTimeout(() => !visible && finish("unavailable"), READY_TIMEOUT_MS)
    tag.cmd.push(() => {
      const slot = tag.defineOutOfPageSlot(UNIT, tag.enums.OutOfPageFormat.REWARDED)
      if (!slot) return finish("unavailable") // this browser or page can't show rewarded ads
      const pubads = tag.pubads()
      const mine = (fn: (e: RewardedEvent) => void) => (e: RewardedEvent) => e.slot === slot && fn(e)
      const onReady = mine((e) => {
        visible = true
        e.makeRewardedVisible?.()
      })
      const onGranted = mine(() => {
        granted = true
      })
      const onClosed = mine(() => finish(granted ? "granted" : "closed"))
      const onRender = mine((e) => e.isEmpty && finish("unavailable"))
      const events: [string, (e: RewardedEvent) => void][] = [
        ["rewardedSlotReady", onReady],
        ["rewardedSlotGranted", onGranted],
        ["rewardedSlotClosed", onClosed],
        ["slotRenderEnded", onRender],
      ]
      events.forEach(([name, fn]) => pubads.addEventListener(name, fn))
      cleanup = () => {
        events.forEach(([name, fn]) => pubads.removeEventListener(name, fn))
        tag.destroySlots([slot])
      }
      slot.addService(pubads)
      tag.enableServices()
      tag.display(slot)
    })
  })
}

/** Development only: a labelled box with a countdown where the ad would be. */
function standIn(seconds: number): Promise<AdResult> {
  return new Promise((resolve) => {
    const box = document.createElement("div")
    box.className = "adbreak"
    box.setAttribute("role", "dialog")
    box.setAttribute("aria-modal", "true")
    box.setAttribute("aria-label", "Test ad")
    const panel = document.createElement("div")
    panel.className = "adbreak__panel"
    const title = document.createElement("strong")
    title.textContent = "Test ad"
    const note = document.createElement("p")
    note.textContent = "No real ad is set up on this build. This box stands in for one."
    const count = document.createElement("p")
    count.className = "adbreak__count"
    const close = document.createElement("button")
    close.type = "button"
    close.className = "link link--muted"
    close.textContent = "Close without the report"
    panel.append(title, note, count, close)
    box.append(panel)
    document.body.append(box)
    let left = Math.max(1, seconds)
    const end = (result: AdResult) => {
      clearInterval(tick)
      box.remove()
      resolve(result)
    }
    const show = () => (count.textContent = `Your report is added in ${left} second${left === 1 ? "" : "s"}`)
    show()
    const tick = setInterval(() => {
      left -= 1
      if (left <= 0) end("granted")
      else show()
    }, 1000)
    close.addEventListener("click", () => end("closed"))
  })
}
