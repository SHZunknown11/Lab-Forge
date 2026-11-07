/**
 * Build-time HTML for each public page. Search engines and AI crawlers often don't run
 * JavaScript, so the server puts this inside <div id="root"> (the app replaces it once it loads).
 * It is the same text people see on the page.
 */
import { renderToStaticMarkup } from "react-dom/server"
import { HomeIntro, InfoPage } from "./components/InfoPage"
import { AUTHOR, AUTHOR_PATH, TAGLINE, faqFor } from "./content"
import { ROUTES, type Route } from "./routes"

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="prerender">
      <header>
        <a href="/">LabForge</a> · <span>{TAGLINE}</span>
      </header>
      <main>{children}</main>
      <footer>
        <a href="/guide">Guide</a> · <a href="/faq">FAQ</a> · <a href="/about">How it works</a> ·{" "}
        <a href="/privacy">Privacy</a> · <a href="/terms">Terms</a> · Made by <a href={AUTHOR_PATH}>{AUTHOR.name}</a>
      </footer>
    </div>
  )
}

export function render(route: Route): string {
  return renderToStaticMarkup(
    <Shell>{route ? <InfoPage route={route} meta={null} /> : <HomeIntro />}</Shell>,
  )
}

export const routes: Route[] = ["", ...ROUTES]
export const seo = { author: AUTHOR, authorPath: AUTHOR_PATH, tagline: TAGLINE, faq: faqFor(10) }
