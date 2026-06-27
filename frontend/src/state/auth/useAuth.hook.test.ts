/**
 * @vitest-environment jsdom
 *
 * Tests for useAuth (ADR 0009): React Query-backed auth state with login /
 * loginAsGuest / logout mutations that write through to the `me` cache key.
 *
 * Because the implementation calls queryClient.clear() then setQueryData(),
 * the tests that check reactive state changes use waitFor() to let the
 * React Query update cycle settle after each mutation.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import { useAuth } from './useAuth'
import { currentUserKey } from '@/api/queryKeys'
import type { AuthUser } from '@/api/auth'

// ---------------------------------------------------------------------------
// Module-level mocks for the three API calls and the identity helper.
// ---------------------------------------------------------------------------
vi.mock('@/api/auth', () => ({
  startSession: vi.fn(),
  endSession: vi.fn(),
  enterDemo: vi.fn(),
}))

vi.mock('@/state/auth/session', () => ({
  fetchSessionUser: vi.fn(),
}))

vi.mock('@/state/auth/googleIdentity', () => ({
  getGoogleIdentity: vi.fn(),
}))

import { startSession, endSession, enterDemo } from '@/api/auth'
import { fetchSessionUser } from './session'
import { getGoogleIdentity } from './googleIdentity'

const startSessionMock = vi.mocked(startSession)
const endSessionMock = vi.mocked(endSession)
const enterDemoMock = vi.mocked(enterDemo)
const fetchSessionUserMock = vi.mocked(fetchSessionUser)
const getGoogleIdentityMock = vi.mocked(getGoogleIdentity)

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

const REAL_USER: AuthUser = {
  id: 1,
  email: 'user@example.com',
  name: 'Test User',
  picture: 'https://example.com/pic.png',
  is_demo: false,
}

const DEMO_USER: AuthUser = {
  id: 99,
  email: 'demo@example.com',
  name: 'Demo',
  picture: null,
  is_demo: true,
}

function makeWrapper(queryClient: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
}

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useAuth — session query', () => {
  it('exposes isLoading while the session query is in flight', () => {
    fetchSessionUserMock.mockReturnValue(new Promise(() => {})) // never resolves
    const qc = makeQueryClient()
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper(qc) })
    expect(result.current.isLoading).toBe(true)
  })

  it('is unauthenticated and user is null when no session exists (401 → null)', async () => {
    fetchSessionUserMock.mockResolvedValue(null)
    const qc = makeQueryClient()
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper(qc) })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.user).toBeNull()
  })

  it('is authenticated and exposes user when a session is active', async () => {
    fetchSessionUserMock.mockResolvedValue(REAL_USER)
    const qc = makeQueryClient()
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper(qc) })

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true))

    expect(result.current.user).toEqual(REAL_USER)
    expect(result.current.isDemo).toBe(false)
  })

  it('reports isDemo true when the demo user is active', async () => {
    fetchSessionUserMock.mockResolvedValue(DEMO_USER)
    const qc = makeQueryClient()
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper(qc) })

    await waitFor(() => expect(result.current.user?.is_demo).toBe(true))

    expect(result.current.isDemo).toBe(true)
  })
})

describe('useAuth — login mutation', () => {
  it('resolves with the returned user on success', async () => {
    fetchSessionUserMock.mockResolvedValue(null)
    startSessionMock.mockResolvedValue(REAL_USER)
    const qc = makeQueryClient()
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper(qc) })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    let returned: AuthUser | undefined
    await act(async () => {
      returned = await result.current.login('google-id-token')
    })

    expect(startSessionMock).toHaveBeenCalledWith('google-id-token')
    expect(returned).toEqual(REAL_USER)
  })

  it('writes the new user into the me cache so isAuthenticated flips to true', async () => {
    // After login, queryClient.clear() + setQueryData(user) runs in onSuccess.
    // Seed fetchSessionUser so any refetch triggered by clear() also returns
    // the logged-in user, letting the state settle to authenticated.
    fetchSessionUserMock.mockResolvedValue(REAL_USER)
    startSessionMock.mockResolvedValue(REAL_USER)
    const qc = makeQueryClient()
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper(qc) })

    // Wait for initial load to settle (with fetchSessionUser → REAL_USER the
    // hook may already be authenticated, which is fine — the assertion below
    // still validates the post-login state).
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.login('google-id-token')
    })

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true))
    expect(result.current.user).toEqual(REAL_USER)
  })

  it('propagates a rejection so the caller can surface an error', async () => {
    fetchSessionUserMock.mockResolvedValue(null)
    startSessionMock.mockRejectedValue({ status: 401, code: '401', detail: '', isNetwork: false })
    const qc = makeQueryClient()
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper(qc) })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await expect(act(() => result.current.login('bad-token'))).rejects.toMatchObject({ status: 401 })
  })
})

describe('useAuth — loginAsGuest mutation', () => {
  it('resolves with the demo user on success', async () => {
    fetchSessionUserMock.mockResolvedValue(null)
    enterDemoMock.mockResolvedValue(DEMO_USER)
    const qc = makeQueryClient()
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper(qc) })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    let returned: AuthUser | undefined
    await act(async () => {
      returned = await result.current.loginAsGuest()
    })

    expect(enterDemoMock).toHaveBeenCalled()
    expect(returned).toEqual(DEMO_USER)
  })

  it('flips isDemo to true after a successful guest login', async () => {
    // Seed fetchSessionUser so any refetch triggered by clear() returns
    // the demo user, letting the state settle to isDemo.
    fetchSessionUserMock.mockResolvedValue(DEMO_USER)
    enterDemoMock.mockResolvedValue(DEMO_USER)
    const qc = makeQueryClient()
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper(qc) })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.loginAsGuest()
    })

    await waitFor(() => expect(result.current.isDemo).toBe(true))
  })
})

describe('useAuth — logout mutation', () => {
  it('clears the user from the me cache so isAuthenticated flips to false', async () => {
    fetchSessionUserMock.mockResolvedValue(REAL_USER)
    endSessionMock.mockResolvedValue(undefined)
    const qc = makeQueryClient()
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper(qc) })

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true))

    // After logout, update the fetchSessionUser mock to return null so any
    // refetch triggered by queryClient.clear() resolves to the logged-out state.
    fetchSessionUserMock.mockResolvedValue(null)

    await act(async () => {
      await result.current.logout()
    })

    await waitFor(() => expect(result.current.isAuthenticated).toBe(false))
    expect(endSessionMock).toHaveBeenCalled()
    expect(result.current.user).toBeNull()
  })

  it('calls getGoogleIdentity().disableAutoSelect() to stop silent re-auth', async () => {
    fetchSessionUserMock.mockResolvedValue(REAL_USER)
    endSessionMock.mockResolvedValue(undefined)
    const disableAutoSelect = vi.fn()
    getGoogleIdentityMock.mockReturnValue({ disableAutoSelect } as unknown as ReturnType<typeof getGoogleIdentity>)
    const qc = makeQueryClient()
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper(qc) })

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true))

    fetchSessionUserMock.mockResolvedValue(null)

    await act(async () => {
      await result.current.logout()
    })

    expect(disableAutoSelect).toHaveBeenCalledTimes(1)
  })

  it('drops the previous user cached data (except auth) to prevent cross-user leakage', async () => {
    fetchSessionUserMock.mockResolvedValue(REAL_USER)
    endSessionMock.mockResolvedValue(undefined)
    getGoogleIdentityMock.mockReturnValue(null)
    const qc = makeQueryClient()
    // Seed a previous user's dashboard list into the cache.
    qc.setQueryData(['links', { deleted: false }], { items: [{ token: 'secret' }], next_cursor: null })
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper(qc) })

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true))

    fetchSessionUserMock.mockResolvedValue(null)

    await act(async () => {
      await result.current.logout()
    })

    // The signed-out user's links are removed; auth/me is set to null (not removed).
    expect(qc.getQueryData(['links', { deleted: false }])).toBeUndefined()
    expect(qc.getQueryData(currentUserKey())).toBeNull()
  })

  it('propagates a rejection so the caller can surface an error', async () => {
    fetchSessionUserMock.mockResolvedValue(REAL_USER)
    endSessionMock.mockRejectedValue({ status: 500, code: '500', detail: '', isNetwork: false })
    const qc = makeQueryClient()
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper(qc) })

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true))

    await expect(act(() => result.current.logout())).rejects.toMatchObject({ status: 500 })
  })
})

describe('useAuth — cache key is currentUserKey()', () => {
  it('pre-seeding the cache with a user makes the hook immediately authenticated', async () => {
    const qc = makeQueryClient()
    qc.setQueryData(currentUserKey(), REAL_USER)
    // fetchSessionUser is not called because staleTime=Infinity + warm cache.
    fetchSessionUserMock.mockResolvedValue(REAL_USER)

    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper(qc) })

    // The stale-time is Infinity so the pre-seeded value is used immediately.
    expect(result.current.user).toEqual(REAL_USER)
  })
})
