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
  const { data } = await apiClient.post<CreateQrResponse>('/qr/create', body)
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
  const { data } = await apiClient.get<GetLinkResponse>(`/qr/${token}`)
  return data
}
