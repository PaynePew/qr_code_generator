import { apiClient } from './client'

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
 * Verify a Google credential server-side and start an app session.
 *
 * The backend verifies the Google ID token once, upserts the User, and sets the
 * httpOnly session cookie on the response — the cookie is never read by JS here.
 */
export async function startSession(credential: string): Promise<AuthUser> {
  const { data } = await apiClient.post<AuthUser>('/api/auth/session', { credential })
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
