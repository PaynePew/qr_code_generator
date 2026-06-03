import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { currentUserKey } from '@/api/queryKeys'
import type { ApiError } from '@/api/client'
import { startSession, endSession, enterDemo, type AuthUser } from '@/api/auth'
import { fetchSessionUser } from './session'
import { getGoogleIdentity } from './googleIdentity'

export interface UseAuthResult {
  user: AuthUser | null
  isLoading: boolean
  isAuthenticated: boolean
  isDemo: boolean
  login: (credential: string) => Promise<AuthUser>
  loginAsGuest: () => Promise<AuthUser>
  logout: () => Promise<void>
}

/**
 * Single source of truth for auth state (ADR 0009). Backed by react-query so the
 * session survives reloads via the cookie: the `me` query reflects the server,
 * login/logout mutations write through to it.
 */
export function useAuth(): UseAuthResult {
  const queryClient = useQueryClient()

  const query = useQuery<AuthUser | null, ApiError>({
    queryKey: currentUserKey(),
    queryFn: () => fetchSessionUser(),
    staleTime: Infinity,
    retry: false,
  })

  const loginMutation = useMutation<AuthUser, ApiError, string>({
    mutationFn: (credential) => startSession(credential),
    onSuccess(user) {
      queryClient.setQueryData(currentUserKey(), user)
    },
  })

  // "Try as guest" — start a session as the shared read-only demo account. Same
  // write-through as a real login so the UI immediately reflects the demo user.
  const guestMutation = useMutation<AuthUser, ApiError>({
    mutationFn: () => enterDemo(),
    onSuccess(user) {
      queryClient.setQueryData(currentUserKey(), user)
    },
  })

  const logoutMutation = useMutation<void, ApiError>({
    mutationFn: () => endSession(),
    onSuccess() {
      // Stop One Tap from silently re-authenticating the just-signed-out user.
      getGoogleIdentity()?.disableAutoSelect()
      queryClient.setQueryData(currentUserKey(), null)
    },
  })

  const user = query.data ?? null

  return {
    user,
    isLoading: query.isLoading,
    isAuthenticated: user !== null,
    isDemo: user?.is_demo ?? false,
    login: (credential) => loginMutation.mutateAsync(credential),
    loginAsGuest: () => guestMutation.mutateAsync(),
    logout: () => logoutMutation.mutateAsync(),
  }
}
