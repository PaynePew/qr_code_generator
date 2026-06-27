/**
 * @vitest-environment jsdom
 *
 * Tests for LoginControl (ADR 0009): the header auth widget.
 *
 * Verified behaviors:
 *  - loading skeleton while session is in flight
 *  - signed-in user: shows name, avatar (when present), sign-out button
 *  - demo user: renders DemoBadge + sign-out button
 *  - signed-out: shows "Try as guest" button; fallback Google button div
 *    when One Tap is unavailable or dismissed
 *  - sign-out click delegates to useAuth().logout
 *  - guest-login click delegates to useAuth().loginAsGuest
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import { LoginControl } from './LoginControl'
import type { AuthUser } from '@/api/auth'

// ---------------------------------------------------------------------------
// Mock useAuth and useGoogleOneTap at the module boundary so LoginControl
// never touches React Query or the Google script.
// ---------------------------------------------------------------------------
vi.mock('@/state/auth', () => ({
  useAuth: vi.fn(),
  useGoogleOneTap: vi.fn(),
}))

// sonner toast is a side-effect; stub it so tests don't require the Toaster.
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }))

import { useAuth, useGoogleOneTap } from '@/state/auth'

const useAuthMock = vi.mocked(useAuth)
const useGoogleOneTapMock = vi.mocked(useGoogleOneTap)

// ---------------------------------------------------------------------------
// Default One Tap stub: neither fallback nor unconfigured.
// ---------------------------------------------------------------------------
const NO_FALLBACK_ONE_TAP = {
  showFallback: false,
  unconfigured: false,
  ready: true,
  renderFallbackButton: vi.fn(),
  renderFallbackIconButton: vi.fn(),
}

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

beforeEach(() => {
  vi.clearAllMocks()
  useGoogleOneTapMock.mockReturnValue(NO_FALLBACK_ONE_TAP)
})

function renderLoginControl() {
  return render(createElement(LoginControl))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('LoginControl — loading state', () => {
  it('renders a loading skeleton while the session query is in flight', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isLoading: true,
      isAuthenticated: false,
      isDemo: false,
      login: vi.fn(),
      loginAsGuest: vi.fn(),
      logout: vi.fn(),
    })

    const { container } = renderLoginControl()

    // The skeleton has aria-hidden so it does not pollute the accessibility tree.
    const skeleton = container.querySelector('[aria-hidden="true"]')
    expect(skeleton).toBeTruthy()
    // No interactive buttons while loading.
    expect(screen.queryByRole('button')).toBeNull()
  })
})

describe('LoginControl — authenticated user', () => {
  it('shows the user name and a sign-out button', () => {
    useAuthMock.mockReturnValue({
      user: REAL_USER,
      isLoading: false,
      isAuthenticated: true,
      isDemo: false,
      login: vi.fn(),
      loginAsGuest: vi.fn(),
      logout: vi.fn(),
    })

    renderLoginControl()

    expect(screen.getByText('Test User')).toBeTruthy()
    expect(screen.getByRole('button', { name: /登出/ })).toBeTruthy()
  })

  it('shows the avatar image when the user has a picture', () => {
    useAuthMock.mockReturnValue({
      user: REAL_USER,
      isLoading: false,
      isAuthenticated: true,
      isDemo: false,
      login: vi.fn(),
      loginAsGuest: vi.fn(),
      logout: vi.fn(),
    })

    const { container } = renderLoginControl()

    const img = container.querySelector('img')
    expect(img).toBeTruthy()
    expect(img?.src).toContain('pic.png')
  })

  it('does not show an avatar when the user has no picture', () => {
    useAuthMock.mockReturnValue({
      user: { ...REAL_USER, picture: null },
      isLoading: false,
      isAuthenticated: true,
      isDemo: false,
      login: vi.fn(),
      loginAsGuest: vi.fn(),
      logout: vi.fn(),
    })

    const { container } = renderLoginControl()

    expect(container.querySelector('img')).toBeNull()
  })

  it('calls logout() when the sign-out button is clicked', async () => {
    const logout = vi.fn().mockResolvedValue(undefined)
    useAuthMock.mockReturnValue({
      user: REAL_USER,
      isLoading: false,
      isAuthenticated: true,
      isDemo: false,
      login: vi.fn(),
      loginAsGuest: vi.fn(),
      logout,
    })

    renderLoginControl()

    fireEvent.click(screen.getByRole('button', { name: /登出/ }))

    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1))
  })
})

describe('LoginControl — demo user', () => {
  it('renders the DemoBadge (唯讀 status) for the demo account', () => {
    useAuthMock.mockReturnValue({
      user: DEMO_USER,
      isLoading: false,
      isAuthenticated: true,
      isDemo: true,
      login: vi.fn(),
      loginAsGuest: vi.fn(),
      logout: vi.fn(),
    })

    renderLoginControl()

    // DemoBadge has role="status" and aria-label="展示帳號，唯讀模式"
    expect(screen.getByRole('status', { name: /唯讀/ })).toBeTruthy()
  })

  it('still shows the sign-out button for demo users', () => {
    useAuthMock.mockReturnValue({
      user: DEMO_USER,
      isLoading: false,
      isAuthenticated: true,
      isDemo: true,
      login: vi.fn(),
      loginAsGuest: vi.fn(),
      logout: vi.fn(),
    })

    renderLoginControl()

    expect(screen.getByRole('button', { name: /登出/ })).toBeTruthy()
  })
})

describe('LoginControl — logged-out state', () => {
  it('shows the "Try as guest" button when not authenticated', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      isDemo: false,
      login: vi.fn(),
      loginAsGuest: vi.fn(),
      logout: vi.fn(),
    })

    renderLoginControl()

    expect(screen.getByRole('button', { name: /以訪客身分試用/ })).toBeTruthy()
  })

  it('calls loginAsGuest() when the "Try as guest" button is clicked', async () => {
    const loginAsGuest = vi.fn().mockResolvedValue(undefined)
    useAuthMock.mockReturnValue({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      isDemo: false,
      login: vi.fn(),
      loginAsGuest,
      logout: vi.fn(),
    })

    renderLoginControl()

    fireEvent.click(screen.getByRole('button', { name: /以訪客身分試用/ }))

    await waitFor(() => expect(loginAsGuest).toHaveBeenCalledTimes(1))
  })

  it('renders the Google sign-in container when One Tap fell back (showFallback=true)', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      isDemo: false,
      login: vi.fn(),
      loginAsGuest: vi.fn(),
      logout: vi.fn(),
    })
    useGoogleOneTapMock.mockReturnValue({
      showFallback: true,
      unconfigured: false,
      ready: true,
      renderFallbackButton: vi.fn(),
      renderFallbackIconButton: vi.fn(),
    })

    renderLoginControl()

    // One variant renders per breakpoint (desktop pill / mobile icon). jsdom has
    // no matchMedia, so useMinWidth defaults to desktop — assert one exists.
    expect(screen.getAllByLabelText('使用 Google 登入').length).toBeGreaterThan(0)
  })

  it('still renders the Google sign-in container when unconfigured=true (no client ID)', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      isDemo: false,
      login: vi.fn(),
      loginAsGuest: vi.fn(),
      logout: vi.fn(),
    })
    useGoogleOneTapMock.mockReturnValue({
      showFallback: false,
      unconfigured: true,
      ready: false,
      renderFallbackButton: vi.fn(),
      renderFallbackIconButton: vi.fn(),
    })

    renderLoginControl()

    expect(screen.getAllByLabelText('使用 Google 登入').length).toBeGreaterThan(0)
  })

  it('always renders the Google sign-in container when logged out, even while One Tap is active', () => {
    // Bug B regression: the Google affordance must be present whenever logged
    // out (One Tap is additive), so logging out never strands the user with
    // only the guest button.
    useAuthMock.mockReturnValue({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      isDemo: false,
      login: vi.fn(),
      loginAsGuest: vi.fn(),
      logout: vi.fn(),
    })
    useGoogleOneTapMock.mockReturnValue({
      showFallback: false,
      unconfigured: false,
      ready: true,
      renderFallbackButton: vi.fn(),
      renderFallbackIconButton: vi.fn(),
    })

    renderLoginControl()

    expect(screen.getAllByLabelText('使用 Google 登入').length).toBeGreaterThan(0)
  })

  it('passes enabled=false to useGoogleOneTap while the session is loading', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isLoading: true,
      isAuthenticated: false,
      isDemo: false,
      login: vi.fn(),
      loginAsGuest: vi.fn(),
      logout: vi.fn(),
    })

    renderLoginControl()

    expect(useGoogleOneTapMock).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: false }),
    )
  })

  it('passes enabled=false to useGoogleOneTap when already authenticated', () => {
    useAuthMock.mockReturnValue({
      user: REAL_USER,
      isLoading: false,
      isAuthenticated: true,
      isDemo: false,
      login: vi.fn(),
      loginAsGuest: vi.fn(),
      logout: vi.fn(),
    })

    renderLoginControl()

    expect(useGoogleOneTapMock).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: false }),
    )
  })
})
