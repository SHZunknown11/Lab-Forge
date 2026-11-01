import { useEffect, useState } from "react"
import type { Field } from "./types"

export function useStored<T>(key: string, initial: T | (() => T)) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key)
      if (raw !== null) return JSON.parse(raw) as T
    } catch {
      /* corrupted or blocked storage: fall back */
    }
    return typeof initial === "function" ? (initial as () => T)() : initial
  })
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value))
    } catch {
      /* storage full or blocked; the app still works for this visit */
    }
  }, [key, value])
  return [value, setValue] as const
}

export function today(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`
}

const EXPERIMENT_FIELDS = new Set(["date", "subject name", "subject code"])

export function defaultFields(labels: string[]): Field[] {
  return labels.map((label, i) => {
    const group = EXPERIMENT_FIELDS.has(label.toLowerCase()) ? "experiment" : "you"
    return {
      id: `f${i}`,
      label,
      value: label.toLowerCase() === "date" ? today() : "",
      group,
    }
  })
}

/** Order used in the document: two fields per line, custom fields last. */
export function documentOrder(fields: Field[]): Field[] {
  return [...fields.filter((f) => !f.custom), ...fields.filter((f) => f.custom)]
}

export interface RecentSubject {
  name: string
  code: string
}

export function uid() {
  return Math.random().toString(36).slice(2, 9)
}
