import { useEffect, useRef } from "react"

const CLIENT = import.meta.env.VITE_ADSENSE_CLIENT as string | undefined
const SLOTS: Record<string, string | undefined> = {
  rail: import.meta.env.VITE_ADSENSE_SLOT_RAIL as string | undefined,
  bench: import.meta.env.VITE_ADSENSE_SLOT_BENCH as string | undefined,
}

declare global {
  interface Window {
    adsbygoogle?: unknown[]
  }
}

let scriptAdded = false
function ensureScript() {
  if (scriptAdded || !CLIENT) return
  scriptAdded = true
  const s = document.createElement("script")
  s.async = true
  s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${CLIENT}`
  s.crossOrigin = "anonymous"
  document.head.appendChild(s)
}

/**
 * Google AdSense unit. Set VITE_ADSENSE_CLIENT (ca-pub-…) and a slot id per
 * placement at build time. Without them nothing renders in production; in
 * development a labelled outline shows where the unit will sit.
 */
export function AdSlot({ placement }: { placement: "rail" | "bench" }) {
  const ref = useRef<HTMLModElement>(null)
  const slot = SLOTS[placement]

  useEffect(() => {
    if (!CLIENT || !slot || !ref.current || ref.current.dataset.loaded) return
    ensureScript()
    ref.current.dataset.loaded = "1"
    try {
      ;(window.adsbygoogle = window.adsbygoogle || []).push({})
    } catch {
      /* blocked by an ad blocker: leave the space empty */
    }
  }, [slot])

  if (!CLIENT || !slot) {
    return import.meta.env.DEV ? (
      <div className={`ad ad--${placement} ad--placeholder`} aria-hidden="true">
        Ad ({placement})
      </div>
    ) : null
  }
  return (
    <aside className={`ad ad--${placement}`} aria-label="Advertisement">
      <ins
        ref={ref}
        className="adsbygoogle"
        style={{ display: "block" }}
        data-ad-client={CLIENT}
        data-ad-slot={slot}
        data-ad-format={placement === "bench" ? "horizontal" : "rectangle"}
        data-full-width-responsive="true"
      />
    </aside>
  )
}
