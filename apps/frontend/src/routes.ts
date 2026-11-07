import { AUTHOR } from "./content"

export type Route = "" | "about" | "privacy" | "terms" | "guide" | "faq" | "mohammad-taha"
export const ROUTES: Exclude<Route, "">[] = ["guide", "faq", "about", "privacy", "terms", "mohammad-taha"]

const TITLES: Record<Exclude<Route, "">, string> = {
  guide: "How to use LabForge",
  faq: "LabForge FAQ",
  about: "How LabForge works",
  privacy: "Privacy policy | LabForge",
  terms: "Terms of use | LabForge",
  "mohammad-taha": `${AUTHOR.name}, creator of LabForge`,
}

export function pageTitle(route: Route) {
  return route ? TITLES[route] : `LabForge: lab reports from your experiment sheet, by ${AUTHOR.name}`
}
