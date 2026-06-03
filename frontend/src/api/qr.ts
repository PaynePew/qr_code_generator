import { apiClient } from './client'

export interface CreateQrRequest {
  url: string
  expires_at?: string | null
}

export interface CreateQrResponse {
  token: string
  short_url: string
  qr_code_url: string
  original_url: string
}

export async function createQr(body: CreateQrRequest): Promise<CreateQrResponse> {
  const { data } = await apiClient.post<CreateQrResponse>('/api/qr/create', body)
  return data
}

export type LinkStatus = 'active' | 'expired' | 'deleted'

export interface GetLinkResponse {
  token: string
  original_url: string
  short_url: string
  qr_code_url: string
  status: LinkStatus
  created_at: string
  updated_at: string
  expires_at: string | null
}

export async function getLink(token: string): Promise<GetLinkResponse> {
  const { data } = await apiClient.get<GetLinkResponse>(`/api/qr/${token}`)
  return data
}

export interface LinkListItem {
  token: string
  original_url: string
  short_url: string
  status: LinkStatus
  scan_count: number
  created_at: string
  expires_at: string | null
}

export interface LinkListResponse {
  items: LinkListItem[]
  next_cursor: string | null
}

/**
 * The owner dashboard list (ADR 0009): the signed-in user's own Links with
 * state + total scan count, newest-first. Soft-deleted Links are excluded
 * unless `deleted` is true (the trash filter). Requires a session (401 anon).
 */
export async function listLinks(deleted = false): Promise<LinkListResponse> {
  const { data } = await apiClient.get<LinkListResponse>('/api/qr', {
    params: deleted ? { deleted: true } : undefined,
  })
  return data
}

export interface PatchLinkRequest {
  original_url?: string
  expires_at?: string | null
}

export async function patchLink(token: string, body: PatchLinkRequest): Promise<GetLinkResponse> {
  const { data } = await apiClient.patch<GetLinkResponse>(`/api/qr/${token}`, body)
  return data
}

export async function deleteLink(token: string): Promise<void> {
  await apiClient.delete(`/api/qr/${token}`)
}

export interface ScanByDay {
  date: string
  count: number
  status_codes: Record<string, number>
}

export interface RecentScan {
  scanned_at: string
  status_code: number
  user_agent: string | null
}

export interface AnalyticsResponse {
  token: string
  timezone: string
  total_scans: number
  scans_by_day: ScanByDay[]
  recent_scans: RecentScan[]
}

export async function getAnalytics(token: string): Promise<AnalyticsResponse> {
  const { data } = await apiClient.get<AnalyticsResponse>(`/api/qr/${token}/analytics`)
  return data
}

// ---------------------------------------------------------------------------
// Customization (ADR 0011)
// ---------------------------------------------------------------------------

export interface StyleRecipe {
  foreground: string
  background: string
  size: number
  dotType: string
  ecl: string
}

export interface CustomizationResponse {
  token: string
  style: StyleRecipe
  image_url: string
  logo_url: string | null
  updated_at: string
}

/** Fetch the owner's style recipe + logo ref for re-editing (owner-only). */
export async function getCustomization(token: string): Promise<CustomizationResponse> {
  const { data } = await apiClient.get<CustomizationResponse>(`/api/qr/${token}/customization`)
  return data
}

export interface SaveCustomizationArgs {
  token: string
  /** Serialisable style recipe (will be JSON-stringified as the ``style`` form field). */
  style: StyleRecipe
  /** Rendered composite QR image blob (PNG). */
  image: Blob
  /** Raw logo blob, if any. */
  logo?: Blob | null
}

export interface SaveCustomizationResponse {
  token: string
  image_key: string
  logo_key: string | null
  updated_at: string
}

/**
 * Upload a customization recipe + rendered composite to the server (owner-only).
 * Uses multipart/form-data as required by PUT /api/qr/{token}/customization.
 */
export async function saveCustomization(args: SaveCustomizationArgs): Promise<SaveCustomizationResponse> {
  const form = new FormData()
  form.append('style', JSON.stringify(args.style))
  form.append('image', args.image, 'composite.png')
  if (args.logo) {
    form.append('logo', args.logo, 'logo')
  }
  const { data } = await apiClient.put<SaveCustomizationResponse>(
    `/api/qr/${args.token}/customization`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data
}
