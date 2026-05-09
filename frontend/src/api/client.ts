import axios, { AxiosError } from 'axios'

export interface ApiError {
  status: number
  code: string
  detail: string
  isNetwork: boolean
}

function normalizeError(err: unknown): ApiError {
  if (axios.isAxiosError(err)) {
    const axiosErr = err as AxiosError<{ code?: string; detail?: string }>
    if (axiosErr.response) {
      return {
        status: axiosErr.response.status,
        code: axiosErr.response.data?.code ?? String(axiosErr.response.status),
        detail: axiosErr.response.data?.detail ?? axiosErr.message,
        isNetwork: false,
      }
    }
    // No response — network-level failure
    return {
      status: 0,
      code: 'NETWORK_ERROR',
      detail: axiosErr.message,
      isNetwork: true,
    }
  }
  return {
    status: 0,
    code: 'UNKNOWN_ERROR',
    detail: String(err),
    isNetwork: false,
  }
}

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api',
  headers: { 'Content-Type': 'application/json' },
})

apiClient.interceptors.response.use(
  (response) => response,
  (err: unknown) => Promise.reject(normalizeError(err)),
)

export { apiClient, normalizeError }
