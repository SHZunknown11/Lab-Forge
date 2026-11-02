import { useRef, useState, type KeyboardEvent } from "react"
import { fileUrl } from "../api"
import type { Draft, Meta, Task } from "../types"

interface Props {
  draft: Draft
  jobId: string
  meta: Meta
  busy: Record<number, string>
  uploading: Record<number, boolean>
  live: Record<number, string>
  onChange: (draft: Draft) => void
  onRun: (index: number) => void
  onUpload: (index: number, files: FileList) => void
  onRewrite: () => void
  rewriting: boolean
}

const STATUS: Record<string, string> = {
  passed: "Ran",
  failed: "Didn't run",
  not_run: "Needs your screenshot",
}

export function Review({ draft, jobId, meta, busy, uploading, live, onChange, onRun, onUpload, onRewrite, rewriting }: Props) {
  const [open, setOpen] = useState<number | null>(() => {
    const firstProblem = draft.tasks.findIndex((t) => t.status !== "passed")
    return firstProblem >= 0 ? firstProblem : null
  })
  const set = (patch: Partial<Draft>) => onChange({ ...draft, ...patch })
  const setTask = (i: number, patch: Partial<Task>) =>
    set({ tasks: draft.tasks.map((t, j) => (j === i ? { ...t, ...patch } : t)) })

  return (
    <div className="review">
      <div className="row">
        <label className="field field--narrow">
          <span>Experiment no.</span>
          <input
            value={draft.experiment_no}
            onChange={(e) => set({ experiment_no: e.target.value, title: `Experiment ${e.target.value}`.trim() })}
          />
        </label>
      </div>
      <label className="field">
        <span>Aim</span>
        <AutoText value={draft.aim} onChange={(aim) => set({ aim })} />
      </label>

      <ol className="tasks">
        {draft.tasks.map((t, i) => {
          const status = busy[i] ? "running" : (live[i] ?? t.status)
          const expanded = open === i
          return (
            <li key={i} className={`task task--${status}`}>
              <button
                type="button"
                className="task__head"
                aria-expanded={expanded}
                onClick={() => setOpen(expanded ? null : i)}
              >
                <span className="task__name">{t.title || `Task ${i + 1}`}</span>
                <span className="task__status">{busy[i] ? busy[i] : STATUS[live[i] ?? t.status]}</span>
              </button>
              {t.note && !busy[i] && <p className="task__note">{t.note}</p>}
              {expanded && (
                <TaskEditor
                  task={t}
                  jobId={jobId}
                  meta={meta}
                  busy={!!busy[i]}
                  uploading={!!uploading[i]}
                  onChange={(patch) => setTask(i, patch)}
                  onRun={() => onRun(i)}
                  onUpload={(files) => onUpload(i, files)}
                />
              )}
            </li>
          )
        })}
      </ol>

      <label className="field">
        <span>Learning outcomes, one per line</span>
        <AutoText
          value={draft.learning_outcomes.join("\n")}
          onChange={(v) => set({ learning_outcomes: v.split("\n") })}
        />
      </label>

      <div className="rewrite">
        <button type="button" className="btn btn--quiet" onClick={onRewrite} disabled={rewriting}>
          {rewriting ? "Writing a new version…" : "Write a different version"}
        </button>
        <p className="hint">Different code and wording, so your report doesn't match a classmate's. Uses one of your daily sheets.</p>
      </div>
    </div>
  )
}

function TaskEditor(props: {
  task: Task
  jobId: string
  meta: Meta
  busy: boolean
  uploading: boolean
  onChange: (patch: Partial<Task>) => void
  onRun: () => void
  onUpload: (files: FileList) => void
}) {
  const { task, onChange } = props
  const [active, setActive] = useState(0)
  const upload = useRef<HTMLInputElement>(null)
  const file = task.files[Math.min(active, task.files.length - 1)]
  const runnable = props.meta.languages.find((l) => l.id === task.language)?.runnable
  const setFile = (code: string) =>
    onChange({ files: task.files.map((f, j) => (j === active ? { ...f, code } : f)) })

  return (
    <div className="task__body">
      <label className="field">
        <span>Heading</span>
        <input value={task.title} onChange={(e) => onChange({ title: e.target.value })} />
      </label>
      <label className="field">
        <span>Problem statement</span>
        <AutoText value={task.problem} onChange={(problem) => onChange({ problem })} />
      </label>
      <label className="field">
        <span>Objectives, one per line</span>
        <AutoText value={task.objectives.join("\n")} onChange={(v) => onChange({ objectives: v.split("\n") })} />
      </label>

      {task.files.length > 0 && (
        <div className="field">
          <span id="code-label">Code</span>
          {task.files.length > 1 && (
            <div className="filetabs" role="tablist" aria-labelledby="code-label">
              {task.files.map((f, j) => (
                <button key={j} type="button" role="tab" aria-selected={j === active} onClick={() => setActive(j)}>
                  {f.name}
                </button>
              ))}
            </div>
          )}
          {file && <CodeArea value={file.code} onChange={setFile} label={file.name} />}
          <small className="hint">Tab indents. Press Esc, then Tab, to move on.</small>
        </div>
      )}

      {runnable && (
        <label className="field">
          <span>Input typed into the program, one value per line</span>
          <textarea className="mono" rows={2} value={task.stdin} onChange={(e) => onChange({ stdin: e.target.value })} />
        </label>
      )}

      {props.busy && (
        <p className="hint" role="status">
          Running your program for the output screenshot. This can take a few minutes. Please wait. You can add your own screenshot meanwhile.
        </p>
      )}

      <div className="task__actions">
        {runnable && (
          <button type="button" className="btn btn--secondary" onClick={props.onRun} disabled={props.busy}>
            {props.busy ? "Running…" : "Run again"}
          </button>
        )}
        <button type="button" className="btn btn--secondary" onClick={() => upload.current?.click()} disabled={props.uploading}>
          {props.uploading ? "Adding…" : "Add screenshot"}
        </button>
        <input
          ref={upload}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files?.length) props.onUpload(e.target.files)
            e.target.value = ""
          }}
        />
      </div>

      {(task.output || task.images.length > 0) && (
        <div className="task__outputs">
          {task.output && (
            <label className="check">
              <input
                type="checkbox"
                checked={task.show_console}
                onChange={(e) => onChange({ show_console: e.target.checked })}
              />
              Include the console output
            </label>
          )}
          {task.images.length > 0 && (
            <ul className="thumbs">
              {task.images.map((name) => (
                <li key={name}>
                  <img src={fileUrl(props.jobId, name)} alt="" />
                  <button
                    type="button"
                    className="thumbs__remove"
                    onClick={() => onChange({ images: task.images.filter((n) => n !== name) })}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

export function AutoText({ value, onChange, rows = 2 }: { value: string; onChange: (v: string) => void; rows?: number }) {
  return (
    <textarea
      rows={Math.min(10, Math.max(rows, value.split("\n").length + Math.floor(value.length / 52)))}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

function CodeArea({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  const released = useRef(false)
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Escape") {
      released.current = true // next Tab leaves the box instead of indenting
      return
    }
    if (e.key !== "Tab" || e.shiftKey || released.current) {
      released.current = false
      return
    }
    e.preventDefault()
    const el = e.currentTarget
    const { selectionStart: s, selectionEnd: end } = el
    const next = value.slice(0, s) + "    " + value.slice(end)
    onChange(next)
    requestAnimationFrame(() => el.setSelectionRange(s + 4, s + 4))
  }
  return (
    <textarea
      className="mono code"
      aria-label={label}
      spellCheck={false}
      rows={Math.min(22, Math.max(6, value.split("\n").length))}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={onKey}
    />
  )
}
