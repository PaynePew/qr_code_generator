import type { ApiError } from '@/api/client'
import type { GetLinkResponse } from '@/api/qr'
import type { DerivedStatus, HistoryEntry } from './types'

export type QueryState =
  | { state: 'loading' }
  | { state: 'success'; data: GetLinkResponse }
  | { state: 'error'; error: ApiError }

export type DerivedView = {
  status: DerivedStatus
  isLoading: boolean
  link: GetLinkResponse | undefined
  queryError: ApiError | null
}

// Rules — see CONTEXT.md "Display priority":
//   1. API 404 → missing
//   2. API has data → server status wins
//   3. Loading + dismissed=true → deleted (synchronous fallback)
//   4. Loading + dismissed=false → loading
export function deriveEntry(row: HistoryEntry, query: QueryState): DerivedView {
  if (query.state === 'error' && query.error.status === 404) {
    return {
      status: 'missing',
      isLoading: false,
      link: undefined,
      queryError: query.error,
    }
  }

  if (query.state === 'success') {
    return {
      status: query.data.status,
      isLoading: false,
      link: query.data,
      queryError: null,
    }
  }

  // No usable API truth (still loading, or non-404 error).
  // dismissed flag is the synchronous fallback per CONTEXT.md.
  const status: DerivedStatus = row.dismissed ? 'deleted' : 'active'
  const isLoading = query.state === 'loading' && !row.dismissed
  const queryError = query.state === 'error' ? query.error : null

  return { status, isLoading, link: undefined, queryError }
}
