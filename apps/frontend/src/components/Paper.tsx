import { useEffect, useRef, useState, type DragEvent } from "react"
import { fileUrl } from "../api"
import type { Draft, Field, RunStatus, Task, TemplateInfo } from "../types"

export interface Progress {
  stages: { stage: string; text: string }[]
  tasks: Record<number, RunStatus | "running">
}

interface Props {
  template?: TemplateInfo
  fields: Field[]
  draft: Draft | null
  jobId: string
  writing: boolean
  progress: Progress
  signature: string
  revealKey: string
  onFieldClick: (id: string) => void
  onDropFile: (file: File) => void
}

const PAGE_WIDTH = 816 // 8.5 in at 96 dpi

export function Paper(props: Props) {
  const { template, fields, draft, writing } = props
  const holder = useRef<HTMLDivElement>(null)
  const [zoom, setZoom] = useState(1)
  const [dragging, setDragging] = useState(false)

  useEffect(() => {
    const el = holder.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => {
      setZoom(Math.min(1, (entry.contentRect.width - 8) / PAGE_WIDTH))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const pairs: Field[][] = []
  for (let i = 0; i < fields.length; i += 2) pairs.push(fields.slice(i, i + 2))

  const title = draft?.title || (draft?.experiment_no ? `Experiment ${draft.experiment_no}` : "Experiment")
  const plain = template?.id === "plain"

  const drop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) props.onDropFile(file)
  }

  return (
    <div className="paper-holder" ref={holder}>
      <article
        className={`paper${plain ? " paper--plain" : ""}${dragging ? " paper--drag" : ""}`}
        style={{ zoom }}
        aria-label="Report preview"
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
      >
        {template?.header_image && <img className="paper__header" src={template.header_image} alt="" />}
        <h2 className="paper__title">{title}</h2>
        <dl className="paper__meta">
          {pairs.map((pair, i) => (
            <div className="paper__meta-row" key={i}>
              {pair.map((f) => (
                <div className="paper__meta-cell" key={f.id}>
                  <dt>{f.label.replace(/:$/, "")}:</dt>{" "}
                  <dd>
                    <button
                      type="button"
                      className={f.value ? "ink" : "blank"}
                      onClick={() => props.onFieldClick(f.id)}
                      aria-label={`Edit ${f.label}`}
                    >
                      {f.value || " "}
                    </button>
                  </dd>
                </div>
              ))}
            </div>
          ))}
        </dl>

        {draft ? (
          <Body {...props} draft={draft} />
        ) : writing ? (
          <div className="paper__writing" role="status" aria-live="polite">
            {props.progress.stages.map((s, i) => (
              <p key={i} className={i === props.progress.stages.length - 1 ? "current" : "done"}>
                {s.text}
              </p>
            ))}
          </div>
        ) : (
          <div className="paper__drop">
            <p className="paper__drop-title">Drop the experiment sheet on this page</p>
            <p>PDF, Word, PowerPoint, plain text, or a .zip of your project folder.</p>
          </div>
        )}
      </article>
    </div>
  )
}

function Body({ draft, jobId, progress, signature, revealKey, template }: Props & { draft: Draft }) {
  const single = draft.tasks.length === 1
  const outcomes = draft.learning_outcomes.filter((o) => o.trim())
  const upper = template?.id !== "plain"
  let n = 1
  return (
    <div className="paper__body reveal" key={revealKey}>
      {single ? (
        <>
          {draft.aim && <Item n={n++} label="Aim" text={draft.aim} top />}
          {draft.tasks[0].problem && distinct(draft.tasks[0].problem, draft.aim) && (
            <Item n={n++} label="Problem Statement" text={draft.tasks[0].problem} top />
          )}
          <TaskBody task={draft.tasks[0]} index={0} start={n} top codeLabel="Implementation/Code"
            jobId={jobId} running={progress.tasks[0] === "running"} signature={signature} />
          {outcomes.length > 0 && (
            <>
              <Item n={n + countBody(draft.tasks[0])} label="Learning Outcome" top />
              <Bullets items={outcomes} />
            </>
          )}
        </>
      ) : (
        <>
          {draft.aim && (
            <p className="paper__aim">
              <b>Aim:</b> {draft.aim}
            </p>
          )}
          {draft.tasks.map((t, i) => (
            <section key={i} className="paper__task">
              <h3 className="paper__task-title">{upper ? (t.title || `Task ${i + 1}`).toUpperCase() : t.title || `Task ${i + 1}`}</h3>
              {t.problem && <Item n={1} label="Problem Statement" text={t.problem} />}
              <TaskBody task={t} index={i} start={t.problem ? 2 : 1} codeLabel="Code" jobId={jobId}
                running={progress.tasks[i] === "running"} signature={signature} />
            </section>
          ))}
          {outcomes.length > 0 && (
            <>
              <p className="paper__outcomes-label">
                <b>Learning Outcomes:</b>
              </p>
              <Bullets items={outcomes} />
            </>
          )}
        </>
      )}
    </div>
  )
}

function countBody(t: Task) {
  return (t.objectives.some((o) => o.trim()) ? 1 : 0) + (t.files.some((f) => f.code.trim()) ? 1 : 0) + 1
}

function TaskBody(p: {
  task: Task
  index: number
  start: number
  top?: boolean
  codeLabel: string
  jobId: string
  running: boolean
  signature: string
}) {
  const { task } = p
  let n = p.start
  const objectives = task.objectives.filter((o) => o.trim())
  const files = task.files.filter((f) => f.code.trim())
  const showConsole = task.show_console && (task.output.trim() || (task.status === "passed" && task.images.length === 0))
  return (
    <>
      {objectives.length > 0 && (
        <>
          <Item n={n++} label="Objective" top={p.top} />
          <Bullets items={objectives} />
        </>
      )}
      {files.length > 0 && (
        <>
          <Item n={n++} label={p.codeLabel} top={p.top} />
          {files.map((f, i) => (
            <div key={i} className="paper__file">
              {files.length > 1 && <p className="paper__file-name">{f.name}:</p>}
              <pre className="paper__code">
                {p.signature ? commentLine(p.signature, task.language, f.name) + "\n" : ""}
                {tidy(f.code, task.language)}
              </pre>
            </div>
          ))}
        </>
      )}
      <Item n={n} label="Output" top={p.top} />
      <div className="paper__output">
        {p.running ? (
          <p className="paper__pending">Running the program…</p>
        ) : (
          <>
            {showConsole && (
              <div className="console" role="img" aria-label="Program output">
                <pre>{task.output || "(the program printed nothing)"}</pre>
              </div>
            )}
            {task.images.map((name) => (
              <img key={name} src={fileUrl(p.jobId, name)} alt="Output screenshot" loading="lazy" />
            ))}
            {!showConsole && task.images.length === 0 && <p className="paper__pending">[Attach output screenshot]</p>}
          </>
        )}
      </div>
    </>
  )
}

function Item({ n, label, text, top }: { n: number; label: string; text?: string; top?: boolean }) {
  return (
    <p className={`paper__item${top ? " paper__item--top" : ""}`}>
      <b>
        {n}. {label}:
      </b>
      {text ? ` ${text}` : ""}
    </p>
  )
}

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="paper__bullets">
      {items.map((o, i) => (
        <li key={i}>{o}</li>
      ))}
    </ul>
  )
}

const BRACE = new Set(["java", "c", "cpp", "javascript", "react"])

function tidy(code: string, language: string) {
  const lines = code.replace(/\r\n/g, "\n").replace(/\t/g, "    ").replace(/^\n+|\n+$/g, "").split("\n").map((l) => l.trimEnd())
  if (BRACE.has(language)) return lines.filter((l) => l.trim()).join("\n")
  return lines.filter((l, i) => l.trim() || (i > 0 && lines[i - 1].trim())).join("\n")
}

function commentLine(text: string, language: string, name: string) {
  const ext = name.toLowerCase().split(".").pop() || ""
  const byExt: Record<string, string> = { py: "# ", r: "# ", sh: "# ", sql: "-- ", m: "% " }
  if (ext === "html" || ext === "htm" || language === "html") return `<!-- ${text} -->`
  if (ext === "css") return `/* ${text} */`
  if (byExt[ext]) return byExt[ext] + text
  if (language === "python" || language === "r" || language === "shell") return `# ${text}`
  return `// ${text}`
}

function distinct(a: string, b: string) {
  const norm = (t: string) => t.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim()
  return norm(a) !== norm(b) && !norm(b).includes(norm(a))
}
