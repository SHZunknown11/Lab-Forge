/**
 * Finished reports, kept on this device only (IndexedDB), never on the server.
 *
 * Every entry is locked with AES-GCM under a key the server gives only to the signed-in
 * account, so someone else using this browser, or signed in as another student, can't open
 * them. Clearing the site's data removes them.
 */

const DB = "labforge"
const STORE = "reports"
const MAX_REPORTS = 40

export interface HistoryItem {
  id: string
  ts: number
  title: string
  subject: string
  docxName: string
  pdfName: string
}

interface Sealed {
  iv: Uint8Array<ArrayBuffer>
  data: ArrayBuffer
}

interface Row {
  id: string
  owner: string
  ts: number
  meta: Sealed
  docx: Sealed
  pdf?: Sealed
}

export const historySupported = () =>
  typeof indexedDB !== "undefined" && typeof crypto !== "undefined" && !!crypto.subtle

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1)
    req.onupgradeneeded = () => {
      const store = req.result.createObjectStore(STORE, { keyPath: "id" })
      store.createIndex("owner", "owner")
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

function done<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function withStore<T>(mode: IDBTransactionMode, work: (store: IDBObjectStore) => Promise<T>): Promise<T> {
  const db = await open()
  try {
    return await work(db.transaction(STORE, mode).objectStore(STORE))
  } finally {
    db.close()
  }
}

const keys = new Map<string, Promise<CryptoKey>>()

function importKey(b64: string): Promise<CryptoKey> {
  let key = keys.get(b64)
  if (!key) {
    const raw = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
    key = crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"])
    keys.set(b64, key)
  }
  return key
}

async function seal(key: CryptoKey, data: ArrayBuffer): Promise<Sealed> {
  const iv = crypto.getRandomValues(new Uint8Array(12))
  return { iv, data: await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, data) }
}

const unseal = (key: CryptoKey, sealed: Sealed) =>
  crypto.subtle.decrypt({ name: "AES-GCM", iv: sealed.iv }, key, sealed.data)

const rowId = (owner: string, job: string) => `${owner}:${job}`

/** Save (or replace) the files of one report. `owner` is the account's email. */
export async function saveReport(
  owner: string,
  keyB64: string,
  item: Omit<HistoryItem, "ts">,
  docx: Blob,
  pdf: Blob | null,
): Promise<void> {
  const key = await importKey(keyB64)
  const ts = Date.now()
  const meta = new TextEncoder().encode(JSON.stringify({ ...item, ts })).buffer as ArrayBuffer
  const row: Row = {
    id: rowId(owner, item.id),
    owner,
    ts,
    meta: await seal(key, meta),
    docx: await seal(key, await docx.arrayBuffer()),
    pdf: pdf ? await seal(key, await pdf.arrayBuffer()) : undefined,
  }
  await withStore("readwrite", async (store) => {
    await done(store.put(row))
    const mine = (await done(store.index("owner").getAll(owner))) as Row[]
    const extra = mine.sort((a, b) => b.ts - a.ts).slice(MAX_REPORTS)
    for (const old of extra) await done(store.delete(old.id))
  })
  // Ask the browser not to clear this storage when the device runs low on space.
  void navigator.storage?.persist?.().catch(() => false)
}

/** This account's reports on this device, newest first. Entries that can't be unlocked are skipped. */
export async function listReports(owner: string, keyB64: string): Promise<HistoryItem[]> {
  const key = await importKey(keyB64)
  const rows = await withStore("readonly", async (store) => (await done(store.index("owner").getAll(owner))) as Row[])
  const items: HistoryItem[] = []
  for (const row of rows) {
    try {
      items.push(JSON.parse(new TextDecoder().decode(await unseal(key, row.meta))) as HistoryItem)
    } catch {
      /* locked with another key: not ours to show */
    }
  }
  return items.sort((a, b) => b.ts - a.ts)
}

export async function reportFile(owner: string, keyB64: string, job: string, kind: "docx" | "pdf"): Promise<Blob> {
  const key = await importKey(keyB64)
  const row = await withStore("readonly", async (store) => (await done(store.get(rowId(owner, job)))) as Row | undefined)
  const sealed = row?.[kind]
  if (!sealed) throw new Error("That file isn't saved on this device.")
  const type = kind === "pdf"
    ? "application/pdf"
    : "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
  return new Blob([await unseal(key, sealed)], { type })
}

export const removeReport = (owner: string, job: string) =>
  withStore("readwrite", (store) => done(store.delete(rowId(owner, job))).then(() => undefined))
