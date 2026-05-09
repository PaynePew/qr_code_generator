export type HistoryEntry = {
  token: string
  originalUrl: string
  createdAt: string // ISO 8601
  dismissed: boolean
}

type StoredData = {
  version: number
  entries: HistoryEntry[]
}

const STORAGE_KEY = 'qr-history-v1'
const SCHEMA_VERSION = 1

function load(storage: Storage): HistoryEntry[] {
  try {
    const raw = storage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as StoredData
    if (parsed.version !== SCHEMA_VERSION) {
      storage.removeItem(STORAGE_KEY)
      return []
    }
    return Array.isArray(parsed.entries) ? parsed.entries : []
  } catch {
    return []
  }
}

function save(entries: HistoryEntry[], storage: Storage): void {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify({ version: SCHEMA_VERSION, entries }))
  } catch {
    // QuotaExceededError or unavailable storage — silently ignore
  }
}

export function addToken(
  entry: Omit<HistoryEntry, 'dismissed'>,
  storage: Storage = localStorage,
): void {
  const entries = load(storage)
  if (entries.some((e) => e.token === entry.token)) return
  entries.push({ ...entry, dismissed: false })
  save(entries, storage)
}

export function listTokens(storage: Storage = localStorage): HistoryEntry[] {
  return load(storage).sort(
    (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
  )
}

export function markDeleted(token: string, storage: Storage = localStorage): void {
  const entries = load(storage)
  const idx = entries.findIndex((e) => e.token === token)
  if (idx === -1) return
  entries[idx] = { ...entries[idx], dismissed: true }
  save(entries, storage)
}

export function removeFromHistory(token: string, storage: Storage = localStorage): void {
  const entries = load(storage).filter((e) => e.token !== token)
  save(entries, storage)
}
