import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  ApiError, cancelJob, createDraft, deleteJob, fetchFile, fileUrl, getMe, getMeta, renderReport, resumeDraft, runTask,
  uploadImage,
} from "./api"
import { Account, creditsLine } from "./components/Account"
import { AdSlot } from "./components/AdSlot"
import { History } from "./components/History"
import { HomeIntro, InfoPage } from "./components/InfoPage"
import { AUTHOR, AUTHOR_PATH } from "./content"
import { Paper, type Progress } from "./components/Paper"
import { Feedback } from "./components/Feedback"
import { Review } from "./components/Review"
import { historySupported, saveReport } from "./history"
import { ROUTES, pageTitle, type Route } from "./routes"
import { defaultFields, documentOrder, today, uid, useStored, type RecentSubject } from "./store"
import type { Draft, DraftEvent, Field, Me, Meta, RenderResult, SavedJob, Task } from "./types"

const EMPTY_PROGRESS: Progress = { stages: [], tasks: {} }

function readRoute(): Route {
  const page = location.pathname.replace(/^\/+|\/+$/g, "") as Route
  return (ROUTES as string[]).includes(page) ? page : ""
}

/** Old links used #/privacy: move them to /privacy. */
function moveLegacyHash() {
  const legacy = location.hash.match(/^#\/?(about|privacy|terms)$/)
  if (legacy) history.replaceState(null, "", `/${legacy[1]}`)
}

/** Real page URLs (/privacy, /guide, ...) so search engines and ad reviewers can see each page. */
function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => {
    moveLegacyHash()
    return readRoute()
  })
  useEffect(() => {
    const on = () => {
      moveLegacyHash()
      setRoute(readRoute())
      window.scrollTo(0, 0)
    }
    // Internal links change the page without reloading the app (and losing a report in progress).
    const click = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
      const a = (e.target as Element | null)?.closest?.("a")
      if (!a || a.target || a.hasAttribute("download")) return
      const url = new URL(a.href, location.href)
      if (url.origin !== location.origin || url.pathname.startsWith("/api/") || url.pathname === "/admin") return
      const page = url.pathname.replace(/^\/+|\/+$/g, "")
      if (page && !(ROUTES as string[]).includes(page)) return
      e.preventDefault()
      if (url.pathname !== location.pathname) history.pushState(null, "", url.pathname)
      on()
    }
    window.addEventListener("popstate", on)
    window.addEventListener("hashchange", on)
    document.addEventListener("click", click)
    return () => {
      window.removeEventListener("popstate", on)
      window.removeEventListener("hashchange", on)
      document.removeEventListener("click", click)
    }
  }, [])
  useEffect(() => {
    document.title = pageTitle(route)
  }, [route])
  return route
}

/** Code or input that changed since the last run: its old output no longer belongs to it. */
function markStale(next: Draft, prev: Draft): Draft {
  let changed = false
  const tasks = next.tasks.map((t, i) => {
    const old = prev.tasks[i]
    if (!old || t.stale) return t
    const same = t.stdin === old.stdin && t.files.length === old.files.length &&
      t.files.every((f, k) => f.code === old.files[k].code && f.name === old.files[k].name)
    if (same) return t
    changed = true
    return { ...t, stale: true }
  })
  return changed ? { ...next, tasks } : next
}

export default function App() {
  const route = useRoute()
  const [meta, setMeta] = useState<Meta | null>(null)
  const [metaError, setMetaError] = useState("")
  const [waking, setWaking] = useState(false)
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
  const [me, setMe] = useState<Me | null>(null)
  const [historyVersion, setHistoryVersion] = useState(0)
  const abort = useRef<AbortController | null>(null)
  const writingJob = useRef("")

  useEffect(() => {
    getMeta(() => setWaking(true))
      .then((m) => {
        setWaking(false)
        setMeta(m)
        if (!m.templates.some((t) => t.id === template)) setTemplate(m.templates[0]?.id ?? "cu-cse")
      })
      .catch((e: Error) => {
        setWaking(false)
        setMetaError(e.message)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const refreshMe = useCallback(() => {
    getMe()
      .then(setMe)
      .catch(() => {})
  }, [])
  useEffect(refreshMe, [refreshMe])

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
        } else if (job.pending) {
          // The page was closed while the report was being written: it carried on, so pick it up.
          void follow(job.id, job.lastSeq ?? -1)
        }
      })
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // Once the programs have run, make the Word file without being asked. It's quick; the PDF
  // (LibreOffice, slow on a small server) is made only when the student asks for it.
  useEffect(() => {
    if (!autoMake || !job || writing || rendering || Object.keys(busy).length || Object.keys(uploading).length) return
    setAutoMake(false)
    void makeFiles(false)
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
    (draft: Draft) => setJob((j) => (j ? { ...j, draft: markStale(draft, j.draft), savedAt: Date.now() } : j)),
    [setJob],
  )
  const changeDraft = useCallback(
    (change: (draft: Draft) => Draft) =>
      setJob((j) => (j ? { ...j, draft: markStale(change(j.draft), j.draft), savedAt: Date.now() } : j)),
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

  interface Flow {
    jobId: string
    draft: Draft | null
    finished: boolean
    failed: boolean
    cached: boolean
    seq: number
  }

  /** What to do with each event of a report being written (first time or picked up again). */
  function onEventFor(flow: Flow) {
    return (e: DraftEvent) => {
      if (typeof e.seq === "number") flow.seq = Math.max(flow.seq, e.seq)
      if (e.type === "job") {
        flow.jobId = e.job
        writingJob.current = e.job
        if (e.details) fillFromSheet(e.details)
      } else if (e.type === "stage") {
        setProgress((p) => ({ ...p, stages: [...p.stages, { stage: e.stage, text: e.text }] }))
      } else if (e.type === "draft") {
        flow.draft = e.draft
        setRevealKey(flow.jobId)
        setProgress((p) => ({ ...p, tasks: Object.fromEntries(e.draft.tasks.map((_, i) => [i, "running"])) }))
        setJob({ id: flow.jobId, draft: e.draft, savedAt: Date.now(), cached: false, pending: true, lastSeq: flow.seq })
      } else if (e.type === "task") {
        setProgress((p) => ({ ...p, tasks: { ...p.tasks, [e.index]: e.status } }))
        setJob((j) => (j && j.id === flow.jobId ? { ...j, lastSeq: flow.seq } : j))
      } else if (e.type === "done") {
        flow.finished = true
        flow.cached = e.cached
        setProgress((p) => ({ ...p, tasks: {} }))
        setJob((j) => ({
          id: flow.jobId,
          draft: keepUploads(e.draft, j?.id === flow.jobId ? j.draft : null),
          savedAt: Date.now(),
          cached: e.cached,
          pending: false,
          lastSeq: flow.seq,
        }))
      } else if (e.type === "error") {
        flow.failed = true
        setError(e.message)
        setJob((j) => (j && j.id === flow.jobId ? { ...j, pending: false } : j))
      }
    }
  }

  /**
   * The connection dropped (phone locked, app switched, network blip) but the server carries on:
   * pick the report up again from the last event we saw. A few tries, a little apart.
   */
  async function reconnect(flow: Flow, signal: AbortSignal): Promise<void> {
    for (let attempt = 0; attempt < 8 && !flow.finished && !flow.failed; attempt++) {
      if (attempt > 0) await new Promise((r) => setTimeout(r, Math.min(1500 * attempt, 8000)))
      if (signal.aborted) throw new DOMException("Aborted", "AbortError")
      try {
        await resumeDraft(flow.jobId, flow.seq, onEventFor(flow), signal)
      } catch (e) {
        if ((e as Error).name === "AbortError") throw e
        if (e instanceof ApiError && e.status === 404) throw e
      }
    }
    if (!flow.finished && !flow.failed) throw new ApiError("Lost the connection to the server. Check your network and try again.", 0)
  }

  /** After a report is written: make the Word file, remember the subject. */
  function afterWriting(flow: Flow) {
    setAutoMake(true)
    const subject = value("subject name")
    if (subject) {
      const code = value("subject code")
      setRecent((r) => [{ name: subject, code }, ...r.filter((s) => s.name !== subject)].slice(0, 8))
    }
    if (!flow.cached) {
      setMeta((m) => (m ? { ...m, limits: { ...m.limits, remaining: Math.max(0, m.limits.remaining - 1) } } : m))
    }
    refreshMe() // one report fewer left
  }

  /** Not signed in (any more), or out of reports: show the account as it now is. */
  function accountProblem(e: unknown) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 402)) refreshMe()
  }

  async function write(fresh = false) {
    if (!fresh && !sheetFile && !sheetText.trim()) {
      setError("Add the experiment sheet first: choose a file or paste its text.")
      return
    }
    if (meta?.auth.required && !me?.user) {
      setError("Sign in with your college email first. It's at the top of this panel.")
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
    const flow: Flow = { jobId: "", draft: null, finished: false, failed: false, cached: false, seq: -1 }
    try {
      try {
        await createDraft(form, onEventFor(flow), ctl.signal)
      } catch (e) {
        if ((e as Error).name === "AbortError" || !flow.jobId) throw e
      }
      if (!flow.finished && !flow.failed) await reconnect(flow, ctl.signal)
      if (flow.failed) {
        setView("edit") // the message is in the sidebar
        return
      }
      afterWriting(flow)
    } catch (e) {
      accountProblem(e)
      if ((e as Error).name !== "AbortError" && !handleExpired(e)) setError((e as Error).message)
      setView("edit")
    } finally {
      setWriting(false)
      setProgress((p) => ({ ...p, tasks: {} }))
      writingJob.current = ""
      if (flow.failed) setTimeout(refreshMe, 1500) // a report that failed gives its credit back
    }
  }

  /** Pick up a report that was still being written when the page was closed. */
  async function follow(jobId: string, after: number) {
    abort.current?.abort()
    const ctl = new AbortController()
    abort.current = ctl
    writingJob.current = jobId
    setWriting(true)
    setError("")
    setProgress({ stages: [{ stage: "resume", text: "Picking your report up where it was" }], tasks: {} })
    const flow: Flow = { jobId, draft: job?.draft ?? null, finished: false, failed: false, cached: false, seq: after }
    try {
      await reconnect(flow, ctl.signal)
      if (!flow.failed) afterWriting({ ...flow, cached: true })
    } catch (e) {
      if ((e as Error).name !== "AbortError" && !handleExpired(e)) {
        setError((e as Error).message)
        setJob((j) => (j && j.id === jobId ? { ...j, pending: false } : j))
      }
    } finally {
      setWriting(false)
      setProgress((p) => ({ ...p, tasks: {} }))
      writingJob.current = ""
    }
  }

  function stop() {
    abort.current?.abort()
    if (writingJob.current) void cancelJob(writingJob.current)
    setJob((j) => (j ? { ...j, pending: false } : j))
  }

  async function removeFromServer() {
    if (!job) return
    if (!window.confirm("Delete this report and its files from the server? Your details and saved reports in this browser stay.")) return
    try {
      await deleteJob(job.id)
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 404)) {
        setRenderError((e as Error).message)
        return
      }
    }
    setJob(null)
    setRender(null)
    setSheetFile(null)
    setSheetText("")
    setView("edit")
    setError("Deleted. The report and its files are gone from the server.")
  }

  async function rerun(index: number) {
    if (!job) return
    setBusy((b) => ({ ...b, [index]: "Running…" }))
    try {
      const task = await runTask(job.id, index, job.draft.tasks[index])
      setJob((j) => (j ? { ...j, draft: { ...j.draft, tasks: j.draft.tasks.map((t, i) => (i === index ? keepUploads(task, t) : t)) } } : j))
      if (render) setAutoMake(true) // the Word file already made should show the new output
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

  async function makeFiles(pdf: boolean) {
    if (!job || !meta) return
    setRendering(true)
    setRenderError("")
    const key = currentKey
    try {
      const result = await renderReport(job.id, {
        draft: job.draft,
        fields: ordered.map(({ label, value }) => ({ label, value })),
        template,
        pdf: pdf && meta.pdf,
        sign_code: signCode,
      })
      setRender(result)
      setRenderKey(key)
      void remember(job.id, job.draft, result)
    } catch (e) {
      if (!handleExpired(e)) setRenderError((e as Error).message)
    } finally {
      setRendering(false)
    }
  }

  /** Keep the finished files on this device, locked to the account. The server deletes its copy. */
  async function remember(jobId: string, draft: Draft, result: RenderResult) {
    if (!me?.user || !me.history_key || !historySupported()) return
    try {
      const docx = await fetchFile(jobId, result.docx, result.render)
      const pdf = result.pdf ? await fetchFile(jobId, result.pdf, result.render) : null
      const numbered = /^\s*experiment\b/i.test(draft.title) // some sheets' titles already say "Experiment 3"
      const title = [!numbered && draft.experiment_no && `Experiment ${draft.experiment_no}`, draft.title]
        .filter(Boolean)
        .join(": ")
      await saveReport(
        me.user.email,
        me.history_key,
        { id: jobId, title, subject: value("subject name"), docxName: result.docx, pdfName: result.pdf ?? "" },
        docx,
        pdf,
      )
      setHistoryVersion((v) => v + 1)
    } catch {
      /* storage blocked or full: the download buttons still work */
    }
  }

  const you = fields.filter((f) => f.group === "you")
  const experiment = fields.filter((f) => f.group === "experiment")
  const needsScreenshot = job?.draft.tasks.filter((t) => !t.output.trim() && t.images.length === 0 && !t.stale).length ?? 0
  const changedTasks = job?.draft.tasks.filter((t) => t.stale).length ?? 0
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
    <div className="app" data-view={route ? "preview" : view}>
      <aside className="rail">
        <header className="brand">
          <a href="/" className="brand__mark" aria-label="LabForge home">
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

        {waking && !meta && (
          <p className="hint" role="status">
            Starting the server. This takes up to a minute after a quiet spell, and then it's quick.
          </p>
        )}
        {metaError && (
          <p className="alert" role="alert">
            {metaError}
          </p>
        )}

        {meta && (meta.auth.required || me?.user) && <Account auth={meta.auth} me={me} onChange={setMe} />}

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
            <button type="button" className="link link--muted" onClick={stop}>
              Stop
            </button>
          )}
          {writing && (
            <p className="hint" role="status">
              Getting the output screenshots can take a few minutes, especially for Java and Spring programs. You can leave
              this page: the report keeps being written and comes back when you return.
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
          {meta && meta.ai_ready && !meta.auth.required && (
            <p className="hint">
              {meta.limits.remaining} of {meta.limits.daily} new sheets left today. Sheets someone already uploaded don't count.
            </p>
          )}
          {meta && meta.auth.required && (
            <p className="hint">
              {me?.user
                ? `${creditsLine(me)}. Writing the same sheet again doesn't use one.`
                : "Sign in at the top of this panel to write a report."}
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
            <p className="hint integrity">
              Before you submit: read the code, run it yourself, and make sure you can explain it in your viva. Follow your
              college's rules on what you may submit.
            </p>
            {(needsScreenshot > 0 || blanks.length > 0 || changedTasks > 0) && (
              <ul className="checklist">
                {changedTasks > 0 && (
                  <li>
                    {changedTasks === 1 ? "One task has" : `${changedTasks} tasks have`} changed code or input. Run{" "}
                    {changedTasks === 1 ? "it" : "them"} again in step 3, or the report will have no output for{" "}
                    {changedTasks === 1 ? "it" : "them"}.
                  </li>
                )}
                {needsScreenshot > 0 && (
                  <li>
                    {needsScreenshot === 1 ? "One program has" : `${needsScreenshot} programs have`} no output yet. Add a
                    screenshot in step 3, or the report will say "Attach output screenshot".
                  </li>
                )}
                {blanks.length > 0 && <li>Still blank: {blanks.join(", ")}.</li>}
              </ul>
            )}
            <button type="button" className="btn btn--primary btn--wide" onClick={() => void makeFiles(meta.pdf)}
              disabled={rendering || writing}>
              {rendering
                ? "Making your files…"
                : render && stale
                  ? "Update the files"
                  : meta.pdf
                    ? render?.pdf ? "Make the files again" : "Make the PDF"
                    : render ? "Make the Word file again" : "Make the Word file"}
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
                {!render.pdf && !render.pdf_error && meta.pdf && (
                  <p className="hint">The Word file is ready. Press "Make the PDF" for a PDF and page previews.</p>
                )}
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
            <div className="row row--between">
              <button type="button" className="link link--muted" onClick={() => {
                setJob(null)
                setRender(null)
                setSheetFile(null)
                setSheetText("")
                setView("edit")
              }}>
                Start a new report
              </button>
              <button type="button" className="link link--muted" onClick={() => void removeFromServer()} disabled={writing}>
                Delete this report from the server
              </button>
            </div>
          </section>
        )}

        {me?.user && me.history_key && (
          <History owner={me.user.email} historyKey={me.history_key} version={historyVersion} />
        )}

        <footer className="railfoot">
          <a href="/guide">Guide</a>
          <a href="/faq">FAQ</a>
          <a href="/about">How it works</a>
          <a href="/privacy">Privacy</a>
          <a href="/terms">Terms</a>
          <p className="railfoot__note">
            Made by <a href={AUTHOR_PATH}>{AUTHOR.name}</a>. Independent project, not affiliated with any university.
          </p>
        </footer>
      </aside>

      <main className="bench">
        {route ? (
          <InfoPage route={route} meta={meta} />
        ) : (
          <>
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
            onChange={job && !writing ? changeDraft : undefined}
            onDropFile={(f) => {
              setSheetFile(f)
              setPasteMode(false)
              setView("edit")
            }}
          />
            {!job && !writing && <HomeIntro />}
          </>
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
