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
  /** When set, the text on the page can be edited in place; the Word and PDF files follow. */
  onChange?: (update: (draft: Draft) => Draft) => void
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
  // Each edit is applied to the latest draft, so two quick edits never overwrite each other.
  const edit = draft && props.onChange ? (patch: Partial<Draft>) => props.onChange!((d) => ({ ...d, ...patch })) : null

  const drop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) props.onDropFile(file)
  }

  return (
    <div className="paper-holder" ref={holder}>
      {edit && (
        <p className="paper-hint">
          Click any text on the page to change it. Program output can't be edited: change the code and run it again.
        </p>
      )}
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
        <h2 className="paper__title">
          <Text value={title} edit={edit && ((v) => edit({ title: v }))} label="Report title" />
        </h2>
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
                      {f.value || " "}
                    </button>
                  </dd>
                </div>
              ))}
            </div>
          ))}
        </dl>

        {draft ? (
          <Body {...props} draft={draft} edit={edit} update={props.onChange ?? null} />
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

type Edit = ((patch: Partial<Draft>) => void) | null
type EditTask = ((change: (task: Task) => Task) => void) | null

function Body({ draft, jobId, progress, signature, revealKey, template, edit, update }: Props & {
  draft: Draft
  edit: Edit
  update: ((change: (draft: Draft) => Draft) => void) | null
}) {
  const single = draft.tasks.length === 1
  const outcomes = draft.learning_outcomes.filter((o) => o.trim())
  const upper = template?.id !== "plain"
  const editTask = (i: number): EditTask =>
    update && ((change) => update((d) => ({ ...d, tasks: d.tasks.map((t, k) => (k === i ? change(t) : t)) })))
  const editOutcomes = edit && ((items: string[]) => edit({ learning_outcomes: items }))
  let n = 1
  return (
    <div className="paper__body reveal" key={revealKey}>
      {single ? (
        <>
          {draft.aim && <Item n={n++} label="Aim" text={draft.aim} top edit={edit && ((v) => edit({ aim: v }))} />}
          {draft.tasks[0].problem && distinct(draft.tasks[0].problem, draft.aim) && (
            <Item n={n++} label="Problem Statement" text={draft.tasks[0].problem} top
              edit={editTask(0) && ((v) => editTask(0)!((t) => ({ ...t, problem: v })))} />
          )}
          <TaskBody task={draft.tasks[0]} index={0} start={n} top codeLabel="Implementation/Code"
            jobId={jobId} running={progress.tasks[0] === "running"} signature={signature} edit={editTask(0)} />
          {outcomes.length > 0 && (
            <>
              <Item n={n + countBody(draft.tasks[0])} label="Learning Outcome" top />
              <Bullets items={outcomes} edit={editOutcomes} />
            </>
          )}
        </>
      ) : (
        <>
          {draft.aim && (
            <p className="paper__aim">
              <b>Aim:</b> <Text value={draft.aim} edit={edit && ((v) => edit({ aim: v }))} label="Aim" multiline />
            </p>
          )}
          {draft.tasks.map((t, i) => (
            <section key={i} className="paper__task">
              <h3 className={`paper__task-title${upper ? " paper__task-title--upper" : ""}`}>
                <Text value={t.title || `Task ${i + 1}`} edit={editTask(i) && ((v) => editTask(i)!((x) => ({ ...x, title: v })))}
                  label={`Task ${i + 1} title`} />
              </h3>
              {t.problem && (
                <Item n={1} label="Problem Statement" text={t.problem}
                  edit={editTask(i) && ((v) => editTask(i)!((x) => ({ ...x, problem: v })))} />
              )}
              <TaskBody task={t} index={i} start={t.problem ? 2 : 1} codeLabel="Code" jobId={jobId}
                running={progress.tasks[i] === "running"} signature={signature} edit={editTask(i)} />
            </section>
          ))}
          {outcomes.length > 0 && (
            <>
              <p className="paper__outcomes-label">
                <b>Learning Outcomes:</b>
              </p>
              <Bullets items={outcomes} edit={editOutcomes} />
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
  edit: EditTask
}) {
  const { task, edit } = p
  let n = p.start
  const objectives = task.objectives.filter((o) => o.trim())
  const files = task.files.filter((f) => f.code.trim())
  // Changed code has no output until it runs again: the server leaves it out of the files too.
  const stale = !!task.stale
  const images = stale ? task.images.filter((n) => n.startsWith("up_")) : task.images
  const showConsole = !stale && task.show_console && (task.output.trim() || (task.status === "passed" && images.length === 0))
  const editFile = (name: string) =>
    edit && ((code: string) => edit((t) => ({ ...t, files: t.files.map((f) => (f.name === name ? { ...f, code } : f)) })))
  return (
    <>
      {objectives.length > 0 && (
        <>
          <Item n={n++} label="Objective" top={p.top} />
          <Bullets items={objectives} edit={edit && ((items) => edit((t) => ({ ...t, objectives: items })))} />
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
                <Text value={tidy(f.code, task.language)} edit={editFile(f.name)} label={`Code of ${f.name}`} multiline code />
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
              <div className="console">
                {/* Never editable: this is what the program really printed. */}
                <pre title="This is what the program printed. Change the code or input and run it again to change it.">
                  {task.output || "(the program printed nothing)"}
                </pre>
              </div>
            )}
            {images.map((name) => (
              <img key={name} src={fileUrl(p.jobId, name)} alt="Output screenshot" loading="lazy" />
            ))}
            {stale && <p className="paper__pending">[Code changed: run it again to get its output]</p>}
            {!stale && !showConsole && images.length === 0 && <p className="paper__pending">[Attach output screenshot]</p>}
          </>
        )}
      </div>
    </>
  )
}

function Item({ n, label, text, top, edit }: {
  n: number
  label: string
  text?: string
  top?: boolean
  edit?: ((value: string) => void) | null
}) {
  return (
    <p className={`paper__item${top ? " paper__item--top" : ""}`}>
      <b>
        {n}. {label}:
      </b>
      {text ? (
        <>
          {" "}
          <Text value={text} edit={edit ?? null} label={label} multiline />
        </>
      ) : null}
    </p>
  )
}

function Bullets({ items, edit }: { items: string[]; edit?: ((items: string[]) => void) | null }) {
  return (
    <ul className="paper__bullets">
      {items.map((o, i) => (
        <li key={i}>
          <Text value={o} label={`Point ${i + 1}`}
            edit={edit ? (v) => edit(items.map((x, k) => (k === i ? v : x)).filter((x) => x.trim())) : null} />
        </li>
      ))}
    </ul>
  )
}

/**
 * Text that becomes editable in place when `edit` is set. The DOM owns the text while it has
 * focus; the new value is reported once, on blur. Enter ends a single-line edit.
 */
function Text({ value, edit, label, multiline, code }: {
  value: string
  edit: ((value: string) => void) | null
  label: string
  multiline?: boolean
  code?: boolean
}) {
  const ref = useRef<HTMLSpanElement>(null)
  const editable = edit !== null
  useEffect(() => {
    const el = ref.current
    if (el && document.activeElement !== el && el.textContent !== value) el.textContent = value
  }, [value, editable])
  if (!edit) return <>{value}</>
  return (
    <span
      ref={ref}
      className={`editable${code ? " editable--code" : ""}`}
      contentEditable="plaintext-only"
      suppressContentEditableWarning
      spellCheck={!code}
      role="textbox"
      aria-label={`Edit ${label}`}
      aria-multiline={multiline}
      onKeyDown={(e) => {
        if (e.key === "Escape" || (!multiline && e.key === "Enter")) {
          e.preventDefault()
          e.currentTarget.blur()
        }
      }}
      onBlur={(e) => {
        const next = (e.currentTarget.innerText || "").replace(/\n+$/, "")
        if (next !== value) edit(next)
      }}
    />
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
