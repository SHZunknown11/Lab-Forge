import { Capacitor } from "@capacitor/core"

/** True inside the Android app (Capacitor WebView), false on the website. */
export const isNative = (): boolean => Capacitor.isNativePlatform()

/** Public website address, for invite links (the app's own origin is https://localhost). */
export const SITE_URL: string = (
  (import.meta.env.VITE_SITE_URL as string | undefined) ||
  (import.meta.env.VITE_API_BASE as string | undefined) ||
  ""
).replace(/\/$/, "")

/**
 * Hand a finished file to the student. On the website it is an ordinary download; in the app a
 * WebView can't download, so the file is written to the app's cache and the Android share sheet
 * opens (Save to Drive, WhatsApp, Files, a Word or PDF viewer...).
 */
export async function saveBlob(blob: Blob, name: string): Promise<void> {
  if (!isNative()) {
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = name
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 10_000)
    return
  }
  const { Filesystem, Directory } = await import("@capacitor/filesystem")
  const { Share } = await import("@capacitor/share")
  const buf = new Uint8Array(await blob.arrayBuffer())
  let bin = ""
  for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000))
  const safe = name.replace(/[^\w.\- ]+/g, "_")
  const written = await Filesystem.writeFile({ path: safe, data: btoa(bin), directory: Directory.Cache })
  await Share.share({ title: safe, url: written.uri, dialogTitle: "Save or share your report" })
}
