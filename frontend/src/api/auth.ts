import { apiClient, type ApiError } from './client'

/**
 * The authenticated User as the backend reports it (ADR 0009 `/api/auth/*`).
 * Mirrors the server's `_user_response`; `is_demo` flags the shared read-only
 * demo account.
 */
export interface AuthUser {
  id: number
  email: string
  name: string
  picture: string | null
  is_demo: boolean
}

/**
 * The backend's distinct code for a mutation rejected because the caller is the
 * read-only demo account (ADR 0009). The frontend keys the "log in to create"
 * nudge on this so it never mistakes read-only for a generic 403/error.
 */
export const DEMO_READ_ONLY_CODE = 'DEMO_READ_ONLY'

/** True when an ApiError is the read-only demo guard (403 DEMO_READ_ONLY). */
export function isDemoReadOnly(err: ApiError | null | undefined): boolean {
  return err?.status === 403 && err.code === DEMO_READ_ONLY_CODE
}

/**
 * Verify a Google credential server-side and start an app session.
 *
 * The backend verifies the Google ID token once, upserts the User, and sets the
 * httpOnly session cookie on the response — the cookie is never read by JS here.
 */
export async function startSession(credential: string): Promise<AuthUser> {
  const { data } = await apiClient.post<AuthUser>('/api/auth/session', { credential })
  return data
}

/**
 * Start a session as the shared read-only demo account ("Try as guest", ADR
 * 0009) — no Google credential. The backend resolves the seeded demo User and
 * sets the same httpOnly session cookie; rejects 503 if the demo is unseeded.
 */
export async function enterDemo(): Promise<AuthUser> {
  const { data } = await apiClient.post<AuthUser>('/api/auth/demo-session')
  return data
}

/** Report the currently signed-in User; rejects with a 401 ApiError when there is no valid session. */
export async function getCurrentUser(): Promise<AuthUser> {
  const { data } = await apiClient.get<AuthUser>('/api/auth/me')
  return data
}

/** End the app session (clears the cookie server-side). */
export async function endSession(): Promise<void> {
  await apiClient.delete('/api/auth/session')
}
