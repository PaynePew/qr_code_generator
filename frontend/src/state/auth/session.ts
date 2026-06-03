import type { ApiError } from '@/api/client'
import { getCurrentUser, type AuthUser } from '@/api/auth'

/**
 * Resolve the current session to a User, or `null` when there is none.
 *
 * A 401 from `/api/auth/me` is the normal "logged out" answer (ADR 0009), so we
 * map it to `null` rather than letting it bubble as a query error. Any other
 * failure is a real problem and is rethrown.
 */
export async function fetchSessionUser(
  getUser: () => Promise<AuthUser> = getCurrentUser,
): Promise<AuthUser | null> {
  try {
    return await getUser()
  } catch (err) {
    if ((err as ApiError).status === 401) return null
    throw err
  }
}
