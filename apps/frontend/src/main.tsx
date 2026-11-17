import { StrictMode, Suspense, lazy } from "react"
import { createRoot } from "react-dom/client"
import "@fontsource/atkinson-hyperlegible-next/400.css"
import "@fontsource/atkinson-hyperlegible-next/700.css"
import "@fontsource/tinos/400.css"
import "@fontsource/tinos/700.css"
import "@fontsource/cousine/400.css"
import "./styles.css"
import App from "./App"
import { isNative } from "./native"

// Android app: dark status-bar icons on the light header, and the back button goes back or exits.
if (isNative()) {
  void import("@capacitor/status-bar").then(({ StatusBar, Style }) => {
    void StatusBar.setStyle({ style: Style.Light })
    void StatusBar.setBackgroundColor({ color: "#eef2ff" })
  })
  void import("@capacitor/app").then(({ App: Native }) => {
    void Native.addListener("backButton", ({ canGoBack }) => {
      if (canGoBack) history.back()
      else void Native.exitApp()
    })
  })
}

const Admin = lazy(() => import("./components/Admin"))
const admin = location.pathname.replace(/\/+$/, "") === "/admin"

// Optional, set at build time. Error reports carry no report contents or form details.
const SENTRY_DSN = (import.meta.env.VITE_SENTRY_DSN as string | undefined)?.trim()
if (SENTRY_DSN && !admin) {
  void import("@sentry/browser").then((Sentry) =>
    Sentry.init({ dsn: SENTRY_DSN, sendDefaultPii: false, tracesSampleRate: 0, environment: import.meta.env.MODE }),
  )
}

// Cookieless page counts (Cloudflare Web Analytics), when a token is set at build time.
const CF_BEACON = (import.meta.env.VITE_CF_BEACON_TOKEN as string | undefined)?.trim()
if (CF_BEACON && !admin) {
  const s = document.createElement("script")
  s.defer = true
  s.src = "https://static.cloudflareinsights.com/beacon.min.js"
  s.dataset.cfBeacon = JSON.stringify({ token: CF_BEACON, spa: true })
  document.head.appendChild(s)
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {admin ? (
      <Suspense fallback={null}>
        <Admin />
      </Suspense>
    ) : (
      <App />
    )}
  </StrictMode>,
)
