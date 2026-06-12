import type { ApiError } from '@/api/client'
import type { GetLinkResponse, LinkStatus } from '@/api/qr'

export type EntryAction<TArgs = void> = ((args: TArgs) => Promise<void>) & {
  readonly isPending: boolean
  readonly error: ApiError | null
}

/**
 * The single-Link view for LinkDetail (ADR 0009). The server is the source of
 * truth: `status` is the server's status (undefined while the query loads or
 * 404s), and `link` is the full response. There is no localStorage-derived
 * `missing` state — a 404 surfaces via `queryError`.
 */
export type DerivedEntry = {
  token: string

  status: LinkStatus | undefined
  isLoading: boolean
  link: GetLinkResponse | undefined
  queryError: ApiError | null

  markDeleted: EntryAction
  updateExpiry: EntryAction<string | null>
  updateUrl: EntryAction<string>
  updateLabel: EntryAction<string | null>
}
