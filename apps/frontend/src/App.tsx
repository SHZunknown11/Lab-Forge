import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { ApiError, createDraft, fileUrl, getMeta, renderReport, runTask, uploadImage } from "./api"
import { AdSlot } from "./components/AdSlot"
import { InfoPage, type Route } from "./components/InfoPage"
import { Paper, type Progress } from "./components/Paper"
import { Feedback } from "./components/Feedback"
import { Review } from "./components/Review"
import { defaultFields, documentOrder, today, uid, useStored, type RecentSubject } from "./store"
import type { Draft, Field, Meta, RenderResult, SavedJob, Task } from "./types"

const EMPTY_PROGRESS: Progress = { stages: [], tasks: {} }

function useRoute(): Route {
  const read = () => (location.hash.replace(/^#\/?/, "") as Route) || ""
  const [route, setRoute] = useState<Route>(read)
  useEffect(() => {
    const on = () => {
      setRoute(read())
      window.scrollTo(0, 0)
    }
    window.addEventListener("hashchange", on)
    return () => window.removeEventListener("hashchange", on)
  }, [])
  return ["about", "privacy", "terms"].includes(route) ? route : ""
}

export default function App() {
  const route = useRoute()
  const [meta, setMeta] = useState<Meta | null>(null)
  const [metaError, setMetaError] = useState("")
  const [fields, setFields] = useStored<Field[]>("lf.fields.v1", [])
  const [template, setTemplate] = useStored("lf.template", "cu-cse")
  const [signCode, setSignCode] = useStored("lf.sign", false)
  const [language, setLanguage] = useStored("lf.language", "auto")
  const [recent, setRecent] = useStored<RecentSubject[]>("lf.subjects", [])
  const [job, setJob] = useStored<SavedJob | null>("lf.job.v1", null)

  const [sheetFile, setSheetFile] = useState<File | null>(null)
  const [sheetText, setSheetText] = useState("")
  const [pasteMode, setPasteMode] = useState(false)
  const [writing, setWriting] = useState(false)
  const [progress, setProgress] = useState<Progress>(EMPTY_PROGRESS)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState<Record<number, string>>({})
  const [uploading, setUploading] = useState<Record<number, boolean>>({})
  const [render, setRender] = useState<RenderResult | null>(null)
  const [renderKey, setRenderKey] = useState("")
  const [rendering, setRendering] = useState(false)
  const [renderError, setRenderError] = useState("")
  const [view, setView] = useState<"edit" | "preview">("edit")
  const [revealKey, setRevealKey] = useState("start")
  const [autoMake, setAutoMake] = useState(false)
  const abort = useRef<AbortController | null>(null)

  useEffect(() => {
    getMeta()
      .then((m) => {
        setMeta(m)
        if (!m.templates.some((t) => t.id === template)) setTemplate(m.templates[0]?.id ?? "cu-cse")
      })
      .catch((e: Error) => setMetaError(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // First visit: default fields. Every visit: the date starts as today.
  useEffect(() => {
    if (!meta) return
    setFields((prev) => {
      const base = prev.length ? prev : defaultFields(meta.default_fields)
      return base.map((f) => (f.label.toLowerCase() === "date" ? { ...f, value: today() } : f))
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta])

  // Drafts older than the server keeps files for can't be downloaded any more.
  useEffect(() => {
    if (job && meta && Date.now() - job.savedAt > meta.job_ttl_hours * 3600 * 1000) setJob(null)
  }, [job, meta, setJob])

  // The server's disk is cleared on every update, so a report the browser remembers may be gone.
  // Say so now, instead of leaving download buttons that return "file wasn't available".
  const checkedJob = useRef("")
  useEffect(() => {
    if (!job || writing || checkedJob.current === job.id) return
    checkedJob.current = job.id
    fetch(`/api/jobs/${job.id}/alive`)
      .then((r) => {
        if (r.status === 404) {
          setJob(null)
          setRender(null)
          setError("This report was cleared from the server when it was updated. Upload the sheet again to rebuild it.")
        }
      })
      .catch(() => {})
  }, [job, writing, setJob])

  const tpl = meta?.templates.find((t) => t.id === template)
  const ordered = useMemo(() => documentOrder(fields), [fields])
  const value = (label: string) => fields.find((f) => f.label.toLowerCase() === label)?.value.trim() ?? ""
  const signature = signCode ? [value("student name"), value("uid")].filter(Boolean).join(" - ") : ""
  const currentKey = JSON.stringify([job?.draft, ordered.map((f) => [f.label, f.value]), template, signCode])
  const stale = !!render && renderKey !== currentKey

  const setField = (id: string, patch: Partial<Field>) =>
    setFields((fs) => fs.map((f) => (f.id === id ? { ...f, ...patch } : f)))

  /** Blank fields take what the sheet's own header says (name, UID, subject, ...). The date stays today's. */
  const fillFromSheet = (details: Record<string, string>) => {
    const found = Object.fromEntries(Object.entries(details).map(([k, v]) => [k.toLowerCase(), v]))
    setFields((fs) =>
      fs.map((f) => {
        const label = f.label.trim().toLowerCase()
        return label !== "date" && !f.value.trim() && found[label] ? { ...f, value: found[label] } : f
      }),
    )
  }

  // Once the programs have run (or been re-run), make the Word and PDF files without being asked.
  useEffect(() => {
    if (!autoMake || !job || writing || rendering || Object.keys(busy).length || Object.keys(uploading).length) return
    setAutoMake(false)
    void makeFiles()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoMake, job, writing, rendering, busy, uploading])

  const focusField = (id: string) => {
    setView("edit")
    requestAnimationFrame(() => {
      const el = document.getElementById(`field-${id}`) as HTMLInputElement | null
      el?.focus()
      el?.scrollIntoView({ block: "center", behavior: "smooth" })
    })
  }

  const updateDraft = useCallback(
    (draft: Draft) => setJob((j) => (j ? { ...j, draft, savedAt: Date.now() } : j)),
    [setJob],
  )

  const handleExpired = (e: unknown) => {
    if (e instanceof ApiError && e.status === 404) {
      setJob(null)
      setError("This report expired on the server. Upload the sheet again to start over.")
      return true
    }
    return false
  }

  async function write(fresh = false) {
    if (!fresh && !sheetFile && !sheetText.trim()) {
      setError("Add the experiment sheet first: choose a file or paste its text.")
      return
    }
    const subject = value("subject name")
    const form = new FormData()
    if (fresh && job) form.append("from_job", job.id) // reuse the sheet already on the server
    else {
      if (sheetFile) form.append("file", sheetFile)
      if (sheetText.trim()) form.append("text", sheetText)
    }
    form.append("language", language)
    form.append("subject", subject)
    form.append("fresh", fresh ? "true" : "false")

    abort.current?.abort()
    const ctl = new AbortController()
    abort.current = ctl
    setWriting(true)
    setError("")
    setRender(null)
    setProgress({ stages: [{ stage: "read", text: "Reading your sheet" }], tasks: {} })
    if (!fresh) setJob(null)
    setView("preview")
    let jobId = ""
    let cached = false
    let failed = false
    let draft: Draft | null = null
    let finished = false
    try {
      let dropped: unknown = null
      try {
        await createDraft(
          form,
          (e) => {
            if (e.type === "job") {
              jobId = e.job
              if (e.details) fillFromSheet(e.details)
            }
            else if (e.type === "stage") setProgress((p) => ({ ...p, stages: [...p.stages, { stage: e.stage, text: e.text }] }))
            else if (e.type === "draft") {
              draft = e.draft
              setRevealKey(jobId)
              setProgress((p) => ({ ...p, tasks: Object.fromEntries(e.draft.tasks.map((_, i) => [i, "running"])) }))
              setJob({ id: jobId, draft: e.draft, savedAt: Date.now(), cached: false })
            } else if (e.type === "task") setProgress((p) => ({ ...p, tasks: { ...p.tasks, [e.index]: e.status } }))
            else if (e.type === "done") {
              finished = true
              cached = e.cached
              setProgress((p) => ({ ...p, tasks: {} }))
              setJob((j) => ({
                id: jobId,
                draft: keepUploads(e.draft, j?.id === jobId ? j.draft : null),
                savedAt: Date.now(),
                cached: e.cached,
              }))
            } else if (e.type === "error") {
              failed = true
              setError(e.message)
            }
          },
          ctl.signal,
        )
      } catch (e) {
        if ((e as Error).name === "AbortError") throw e
        dropped = e
      }
      if (failed) {
        setView("edit") // the message is in the sidebar
        return
      }
      if (draft && !finished) {
        // The connection dropped after the draft but before the run results arrived.
        // Run the programs again here so no task is left without output.
        setProgress((p) => ({ ...p, stages: [...p.stages, { stage: "run", text: "Running the programs again" }] }))
        if (!(await runAll(jobId, draft))) return
      } else if (dropped) throw dropped
      setAutoMake(true) // nothing left for the student to click: make the Word and PDF files now
      if (subject) {
        const code = value("subject code")
        setRecent((r) => [{ name: subject, code }, ...r.filter((s) => s.name !== subject)].slice(0, 8))
      }
      if (!cached) {
        setMeta((m) => (m ? { ...m, limits: { ...m.limits, remaining: Math.max(0, m.limits.remaining - 1) } } : m))
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message)
      setView("edit")
    } finally {
      setWriting(false)
      setProgress((p) => ({ ...p, tasks: {} }))
    }
  }

  /** Runs every task of `draft` on the server, one at a time. False when the job expired. */
  async function runAll(jobId: string, draft: Draft): Promise<boolean> {
    for (let i = 0; i < draft.tasks.length; i++) {
      if (!draft.tasks[i].files.some((f) => f.code.trim())) continue
      setProgress((p) => ({ ...p, tasks: { ...p.tasks, [i]: "running" } }))
      try {
        const task = await runTask(jobId, i, draft.tasks[i])
        setJob((j) => (j && j.id === jobId
          ? { ...j, draft: { ...j.draft, tasks: j.draft.tasks.map((t, k) => (k === i ? keepUploads(task, t) : t)) }, savedAt: Date.now() }
          : j))
        setProgress((p) => ({ ...p, tasks: { ...p.tasks, [i]: task.status } }))
      } catch (e) {
        if (handleExpired(e)) return false
        throw e
      }
    }
    return true
  }

  async function rerun(index: number) {
    if (!job) return
    setBusy((b) => ({ ...b, [index]: "Running…" }))
    try {
      const task = await runTask(job.id, index, job.draft.tasks[index])
      setJob((j) => (j ? { ...j, draft: { ...j.draft, tasks: j.draft.tasks.map((t, i) => (i === index ? keepUploads(task, t) : t)) } } : j))
      if (render) setAutoMake(true) // the files already made should show the new output
    } catch (e) {
      if (!handleExpired(e)) setError((e as Error).message)
    } finally {
      setBusy((b) => withoutKey(b, index))
    }
  }

  async function upload(index: number, list: FileList) {
    if (!job) return
    setUploading((u) => ({ ...u, [index]: true }))
    try {
      const names: string[] = []
      for (const f of Array.from(list)) names.push((await uploadImage(job.id, f)).name)
      setJob((j) =>
        j
          ? {
              ...j,
              draft: {
                ...j.draft,
                tasks: j.draft.tasks.map((t, i) => (i === index ? { ...t, images: [...t.images, ...names] } : t)),
              },
            }
          : j,
      )
      if (render) setAutoMake(true)
    } catch (e) {
      if (!handleExpired(e)) setError((e as Error).message)
    } finally {
      setUploading((u) => withoutKey(u, index))
    }
  }

  async function makeFiles() {
    if (!job || !meta) return
    setRendering(true)
    setRenderError("")
    const key = currentKey
    try {
      const result = await renderReport(job.id, {
        draft: job.draft,
        fields: ordered.map(({ label, value }) => ({ label, value })),
        template,
        pdf: meta.pdf,
        sign_code: signCode,
      })
      setRender(result)
      setRenderKey(key)
    } catch (e) {
      if (!handleExpired(e)) setRenderError((e as Error).message)
    } finally {
      setRendering(false)
    }
  }

  const you = fields.filter((f) => f.group === "you")
  const experiment = fields.filter((f) => f.group === "experiment")
  const needsScreenshot = job?.draft.tasks.filter((t) => !t.output.trim() && t.images.length === 0).length ?? 0
  const blanks = ordered.filter((f) => f.label.trim() && !f.value.trim()).map((f) => f.label)
  // While the report is being written, the draft isn't updated yet: show each finished task's real result.
  const finishedNow: Record<number, string> = Object.fromEntries(
    Object.entries(progress.tasks).filter(([, st]) => st !== "running"),
  )
  const runningNow: Record<number, string> = Object.fromEntries(
    Object.entries(progress.tasks)
      .filter(([, s]) => s === "running")
      .map(([i]) => [Number(i), "Running…"]),
  )

  return (
    <div className="app" data-view={view}>
      <aside className="rail">
        <header className="brand">
          <a href="#/" className="brand__mark" aria-label="LabForge home">
            <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">
              <rect x="5" y="2" width="22" height="28" rx="2" fill="#fff" stroke="currentColor" strokeWidth="2" />
              <path d="M10 2v28" stroke="var(--margin)" strokeWidth="1.6" />
              <path d="M13 10h10M13 15h10M13 20h6" stroke="var(--ink)" strokeWidth="2" strokeLinecap="round" />
            </svg>
            LabForge
          </a>
          <p className="brand__line">Your experiment sheet in, a finished lab report out.</p>
        </header>

        <div className="viewswitch" role="tablist" aria-label="Screen">
          <button role="tab" aria-selected={view === "edit"} onClick={() => setView("edit")}>
            Fill in
          </button>
          <button role="tab" aria-selected={view === "preview"} onClick={() => setView("preview")}>
            Preview
          </button>
        </div>

        {metaError && (
          <p className="alert" role="alert">
            {metaError}
          </p>
        )}

        <section className="step" aria-labelledby="s1">
          <h2 id="s1">
            <span className="step__n">1</span>Your details
          </h2>
          <p className="hint">Saved in this browser for next time.</p>
          <div className="fields">
            {you.map((f) => (
              <FieldRow key={f.id} field={f} onChange={(p) => setField(f.id, p)}
                onRemove={f.label.toLowerCase() === "student name" ? undefined : () => setFields((fs) => fs.filter((x) => x.id !== f.id))} />
            ))}
          </div>
          <div className="row row--between">
            <button type="button" className="link" onClick={() =>
              setFields((fs) => [...fs, { id: uid(), label: "", value: "", group: "you", custom: true }])}>
              Add a field
            </button>
            {meta && (
              <button type="button" className="link link--muted" onClick={() =>
                setFields(defaultFields(meta.default_fields).map((d) => ({ ...d, value: fields.find((f) => f.label === d.label)?.value ?? d.value })))}>
                Reset fields
              </button>
            )}
          </div>
          {meta && (
            <fieldset className="choice">
              <legend>Report format</legend>
              {meta.templates.map((t) => (
                <label key={t.id} className="choice__opt">
                  <input type="radio" name="template" checked={template === t.id} onChange={() => setTemplate(t.id)} />
                  <span>
                    <strong>{t.name}</strong>
                    <small>{t.description}</small>
                  </span>
                </label>
              ))}
            </fieldset>
          )}
        </section>

        <section className="step" aria-labelledby="s2">
          <h2 id="s2">
            <span className="step__n">2</span>Experiment sheet
          </h2>
          <div className="fields">
            {experiment.map((f) => (
              <FieldRow key={f.id} field={f} list={f.label.toLowerCase() === "subject name" ? "recent-subjects" : undefined}
                onChange={(p) => {
                  setField(f.id, p)
                  if (f.label.toLowerCase() === "subject name" && p.value !== undefined) {
                    const match = recent.find((s) => s.name === p.value)
                    const codeField = fields.find((x) => x.label.toLowerCase() === "subject code")
                    if (match && codeField) setField(codeField.id, { value: match.code })
                  }
                }} />
            ))}
            <datalist id="recent-subjects">
              {recent.map((s) => (
                <option key={s.name} value={s.name} />
              ))}
            </datalist>
          </div>

          {pasteMode ? (
            <label className="field">
              <span>Experiment text</span>
              <textarea rows={7} value={sheetText} placeholder="Paste the aim and the questions from the LMS…"
                onChange={(e) => setSheetText(e.target.value)} />
            </label>
          ) : (
            <label className={`dropzone${sheetFile ? " dropzone--has" : ""}`}>
              <input
                type="file"
                accept=".pdf,.docx,.pptx,.txt,.md,.zip,.html,.java,.py,.js,.jsx,.c,.cpp,.m,.sql"
                onChange={(e) => setSheetFile(e.target.files?.[0] ?? null)}
              />
              {sheetFile ? (
                <>
                  <strong>{sheetFile.name}</strong>
                  <small>{(sheetFile.size / 1024).toFixed(0)} KB. Choose another file to replace it.</small>
                </>
              ) : (
                <>
                  <strong>Choose the sheet</strong>
                  <small>PDF, Word, PowerPoint, text, or a .zip of your project. You can also drop it on the page.</small>
                </>
              )}
            </label>
          )}
          <button type="button" className="link" onClick={() => setPasteMode((m) => !m)}>
            {pasteMode ? "Upload a file instead" : "Paste the text instead"}
          </button>

          <label className="field field--inline">
            <span>Programming language</span>
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="auto">As the sheet says</option>
              {meta?.languages.filter((l) => l.id !== "other").map((l) => (
                <option key={l.id} value={l.id}>
                  {l.label}
                </option>
              ))}
            </select>
          </label>

          <button type="button" className="btn btn--primary btn--wide" onClick={() => write(false)} disabled={writing || !meta}>
            {writing ? "Writing your report…" : "Write my report"}
          </button>
          {writing && (
            <button type="button" className="link link--muted" onClick={() => abort.current?.abort()}>
              Stop
            </button>
          )}
          {writing && (
            <p className="hint" role="status">
              Getting the output screenshots can take a few minutes, especially for Java and Spring programs. Please wait, and keep this page open.
            </p>
          )}
          {error && (
            <p className="alert" role="alert">
              {error}
            </p>
          )}
          {meta && !meta.ai_ready && (
            <p className="hint">The server has no AI key yet, so only sheets that were written before will work.</p>
          )}
          {meta && meta.ai_ready && (
            <p className="hint">
              {meta.limits.remaining} of {meta.limits.daily} new sheets left today. Sheets someone already uploaded don't count.
            </p>
          )}
        </section>

        <AdSlot placement="rail" />

        {job && meta && (
          <section className="step" aria-labelledby="s3">
            <h2 id="s3">
              <span className="step__n">3</span>Check the report (optional)
            </h2>
            {job.cached && <p className="hint">This sheet was written before, so it came back instantly.</p>}
            <Review
              key={job.id}
              draft={job.draft}
              jobId={job.id}
              meta={meta}
              busy={writing ? runningNow : busy}
              uploading={uploading}
              live={writing ? finishedNow : {}}
              onChange={updateDraft}
              onRun={rerun}
              onUpload={upload}
              onRewrite={() => write(true)}
              rewriting={writing}
            />
          </section>
        )}

        {job && meta && (
          <section className="step" aria-labelledby="s4">
            <h2 id="s4">
              <span className="step__n">4</span>Download
            </h2>
            <label className="check">
              <input type="checkbox" checked={signCode} onChange={(e) => setSignCode(e.target.checked)} />
              Put my name and UID as a comment at the top of the code
            </label>
            {(needsScreenshot > 0 || blanks.length > 0) && (
              <ul className="checklist">
                {needsScreenshot > 0 && (
                  <li>
                    {needsScreenshot === 1 ? "One program has" : `${needsScreenshot} programs have`} no output yet. Add a
                    screenshot in step 3, or the report will say "Attach output screenshot".
                  </li>
                )}
                {blanks.length > 0 && <li>Still blank: {blanks.join(", ")}.</li>}
              </ul>
            )}
            <button type="button" className="btn btn--primary btn--wide" onClick={makeFiles} disabled={rendering || writing}>
              {rendering ? "Making your files…" : render && !stale ? "Make the files again" : render ? "Update the files" : "Make the Word and PDF files"}
            </button>
            {renderError && (
              <p className="alert" role="alert">
                {renderError}
              </p>
            )}
            {render && (
              <div className={`downloads${stale ? " downloads--stale" : ""}`}>
                {stale && <p className="hint">You've changed something since these were made. Update them first.</p>}
                <div className="row">
                  <a className="btn btn--secondary" href={fileUrl(job.id, render.docx, render.render)} download>
                    Download Word file
                  </a>
                  {render.pdf && (
                    <a className="btn btn--secondary" href={fileUrl(job.id, render.pdf, render.render)} download>
                      Download PDF
                    </a>
                  )}
                </div>
                {render.pdf_error && <p className="hint">{render.pdf_error}</p>}
                {render.pages.length > 0 && (
                  <>
                    <p className="hint">
                      {render.pages.length} {render.pages.length === 1 ? "page" : "pages"}, exactly as they'll print:
                    </p>
                    <ol className="pages">
                      {render.pages.map((p, i) => (
                        <li key={p}>
                          <a href={fileUrl(job.id, render.pdf!, render.render)} target="_blank" rel="noopener">
                            <img src={fileUrl(job.id, p, render.render)} alt={`Page ${i + 1}`} loading="lazy" />
                          </a>
                        </li>
                      ))}
                    </ol>
                  </>
                )}
                <Feedback key={job.id} jobId={job.id} />
              </div>
            )}
            <button type="button" className="link link--muted" onClick={() => {
              setJob(null)
              setRender(null)
              setSheetFile(null)
              setSheetText("")
              setView("edit")
            }}>
              Start a new report
            </button>
          </section>
        )}

        <footer className="railfoot">
          <a href="#/about">How it works</a>
          <a href="#/privacy">Privacy</a>
          <a href="#/terms">Terms</a>
        </footer>
      </aside>

      <main className="bench">
        {route ? (
          <InfoPage route={route} ttl={meta?.job_ttl_hours ?? 24} />
        ) : (
          <Paper
            template={tpl}
            fields={ordered}
            draft={job?.draft ?? null}
            jobId={job?.id ?? ""}
            writing={writing}
            progress={progress}
            signature={signature}
            revealKey={revealKey}
            onFieldClick={focusField}
            onDropFile={(f) => {
              setSheetFile(f)
              setPasteMode(false)
              setView("edit")
            }}
          />
        )}
        <AdSlot placement="bench" />
      </main>
    </div>
  )
}

function FieldRow({ field, onChange, onRemove, list }: {
  field: Field
  onChange: (patch: Partial<Field>) => void
  onRemove?: () => void
  list?: string
}) {
  return (
    <div className="fieldrow">
      {field.custom ? (
        <input className="fieldrow__label-input" aria-label="Field name" placeholder="Field name, e.g. Roll No."
          value={field.label} onChange={(e) => onChange({ label: e.target.value })} />
      ) : (
        <label className="fieldrow__label" htmlFor={`field-${field.id}`}>
          {field.label}
        </label>
      )}
      <input id={`field-${field.id}`} value={field.value} list={list} autoComplete="off"
        aria-label={field.custom ? field.label || "Value" : undefined}
        onChange={(e) => onChange({ value: e.target.value })} />
      {onRemove && (
        <button type="button" className="fieldrow__remove" onClick={onRemove} aria-label={`Remove ${field.label || "field"}`}>
          ×
        </button>
      )}
    </div>
  )
}

function withoutKey<T>(record: Record<number, T>, key: number): Record<number, T> {
  const next = { ...record }
  delete next[key]
  return next
}

/** Screenshots the student added while a run was in flight must survive the run's result replacing the task. */
function keepUploads<T extends Draft | Task>(next: T, current: T | null | undefined): T {
  if (!current) return next
  if ("tasks" in next && "tasks" in current) {
    return { ...next, tasks: next.tasks.map((t, i) => keepUploads(t, current.tasks[i])) } as T
  }
  const a = next as Task
  const b = current as Task
  const extra = (b.images ?? []).filter((n) => !a.images.includes(n))
  return extra.length ? ({ ...a, images: [...a.images, ...extra] } as T) : next
}
