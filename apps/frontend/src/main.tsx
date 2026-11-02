import { StrictMode, Suspense, lazy } from "react"
import { createRoot } from "react-dom/client"
import "@fontsource/atkinson-hyperlegible-next/400.css"
import "@fontsource/atkinson-hyperlegible-next/700.css"
import "@fontsource/tinos/400.css"
import "@fontsource/tinos/700.css"
import "@fontsource/cousine/400.css"
import "./styles.css"
import App from "./App"

const Admin = lazy(() => import("./components/Admin"))
const admin = location.pathname.replace(/\/+$/, "") === "/admin"

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
