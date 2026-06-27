import axios, { AxiosError } from 'axios'

export interface ApiError {
  status: number
  code: string
  detail: string
  isNetwork: boolean
}

function normalizeError(err: unknown): ApiError {
  if (axios.isAxiosError(err)) {
    // The backend wraps every error in the unified envelope (ADR 0012):
    //   { "error": { "code", "message", "details" } }
    // Read from `error.*`, not the top level — reading `data.code`/`data.detail`
    // silently missed the envelope, so `code` fell back to the numeric status and
    // code-based branching (e.g. the DEMO_READ_ONLY nudge) never matched.
    const axiosErr = err as AxiosError<{
      error?: { code?: string; message?: string; details?: unknown }
    }>
    if (axiosErr.response) {
      const body = axiosErr.response.data?.error
      return {
        status: axiosErr.response.status,
        code: body?.code ?? String(axiosErr.response.status),
        detail: body?.message ?? axiosErr.message,
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
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  headers: { 'Content-Type': 'application/json' },
  // Send the httpOnly session cookie with every request (ADR 0009). In dev this
  // rides the same-origin Vite proxy; in prod the SPA and API share an origin.
  withCredentials: true,
})

apiClient.interceptors.response.use(
  (response) => response,
  (err: unknown) => Promise.reject(normalizeError(err)),
)

export { apiClient, normalizeError }
