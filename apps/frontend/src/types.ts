export type RunStatus = "passed" | "failed" | "not_run"

export interface CodeFile {
  name: string
  code: string
}

export interface Task {
  title: string
  problem: string
  objectives: string[]
  language: string
  files: CodeFile[]
  stdin: string
  output: string
  status: RunStatus
  note: string
  images: string[]
  show_console: boolean
  /** Browser-only: the code or input changed since the last run, so the output no longer matches. */
  stale?: boolean
}

export interface Draft {
  experiment_no: string
  title: string
  aim: string
  tasks: Task[]
  learning_outcomes: string[]
}

export interface Field {
  id: string
  label: string
  value: string
  group: "you" | "experiment"
  custom?: boolean
}

export interface TemplateInfo {
  id: string
  name: string
  description: string
  header_image: string | null
}

export interface Meta {
  templates: TemplateInfo[]
  default_fields: string[]
  languages: { id: string; label: string; runnable: boolean }[]
  pdf: boolean
  ai_ready: boolean
  limits: { daily: number; remaining: number }
  job_ttl_hours: number
  log_days: number
  log_personal: boolean
}

export interface Explanation {
  summary: string
  steps: string[]
  viva: { q: string; a: string }[]
}

export interface RenderResult {
  render: string
  docx: string
  pdf: string | null
  pdf_error?: string
  pages: string[]
  warnings: string[]
}

export type DraftEvent = { seq?: number } & (
  | { type: "job"; job: string; details?: Record<string, string> }
  | { type: "ping" }
  | { type: "stage"; stage: string; text: string }
  | { type: "draft"; draft: Draft }
  | { type: "task"; index: number; title: string; status: RunStatus; note: string }
  | { type: "done"; draft: Draft; cached: boolean }
  | { type: "error"; message: string }
)

export interface SavedJob {
  id: string
  draft: Draft
  savedAt: number
  cached: boolean
  /** Still being written on the server when this was saved: pick it up again on the next visit. */
  pending?: boolean
  lastSeq?: number
}
