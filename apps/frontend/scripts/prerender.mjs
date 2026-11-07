// Writes dist/prerender/<page>.html and dist/prerender/seo.json from the SSR build.
import { mkdirSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"

const here = dirname(fileURLToPath(import.meta.url))
const ssr = await import(pathToFileURL(join(here, "..", "dist-ssr", "prerender.js")).href)
const out = join(here, "..", "dist", "prerender")
mkdirSync(out, { recursive: true })
for (const route of ssr.routes) {
  writeFileSync(join(out, `${route || "home"}.html`), ssr.render(route))
}
writeFileSync(join(out, "seo.json"), JSON.stringify(ssr.seo, null, 2))
console.log(`prerendered ${ssr.routes.length} pages`)
