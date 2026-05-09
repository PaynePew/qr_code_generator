import type { ApiError } from '@/api/client'
import type { GetLinkResponse, LinkStatus } from '@/api/qr'

export type HistoryEntry = {
  token: string
  originalUrl: string
  createdAt: string
  dismissed: boolean
}

export type DerivedStatus = LinkStatus | 'missing'

export type EntryAction<TArgs = void> = ((args: TArgs) => Promise<void>) & {
  readonly isPending: boolean
  readonly error: ApiError | null
}

export type DerivedEntry = {
  token: string
  originalUrl: string
  createdAt: string

  status: DerivedStatus
  isLoading: boolean
  link: GetLinkResponse | undefined
  queryError: ApiError | null

  markDeleted: EntryAction
  reactivate: EntryAction<string>
  updateExpiry: EntryAction<string | null>
  updateUrl: EntryAction<string>
  removeFromHistory: () => void
}
