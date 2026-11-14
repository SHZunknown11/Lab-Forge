import { useEffect, useState } from "react"
import { historySupported, listReports, removeReport, reportFile, type HistoryItem } from "../history"

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

/** Reports this account made on this device. They're stored here, locked, and nowhere else. */
export function History({ owner, historyKey, version }: { owner: string; historyKey: string; version: number }) {
  const [items, setItems] = useState<HistoryItem[]>([])
  const [error, setError] = useState("")

  useEffect(() => {
    if (!historySupported()) return
    let live = true
    listReports(owner, historyKey)
      .then((list) => live && setItems(list))
      .catch(() => live && setItems([]))
    return () => {
      live = false
    }
  }, [owner, historyKey, version])

  if (!historySupported() || items.length === 0) return null

  const save = async (item: HistoryItem, kind: "docx" | "pdf") => {
    setError("")
    try {
      download(await reportFile(owner, historyKey, item.id, kind), kind === "pdf" ? item.pdfName : item.docxName)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <section className="step history" aria-labelledby="history-title">
      <h2 id="history-title">Your reports</h2>
      <p className="hint">Saved on this device only, locked to your account. They aren't kept on our server.</p>
      <ul className="history__list">
        {items.map((item) => (
          <li key={item.id}>
            <span className="history__what">
              <b>{item.title || "Lab report"}</b>
              <small>
                {[item.subject, new Date(item.ts).toLocaleDateString()].filter(Boolean).join(" · ")}
              </small>
            </span>
            <span className="history__get">
              <button type="button" className="link" onClick={() => void save(item, "docx")}>Word</button>
              {item.pdfName && (
                <button type="button" className="link" onClick={() => void save(item, "pdf")}>PDF</button>
              )}
              <button type="button" className="link link--muted" aria-label={`Remove ${item.title || "report"} from this device`}
                onClick={() => {
                  if (!window.confirm("Remove this report from this device? It can't be brought back.")) return
                  void removeReport(owner, item.id).then(() => setItems((list) => list.filter((x) => x.id !== item.id)))
                }}>
                Remove
              </button>
            </span>
          </li>
        ))}
      </ul>
      {error && <p className="alert" role="alert">{error}</p>}
    </section>
  )
}
