/**
 * @vitest-environment jsdom
 *
 * Tests for useGoogleOneTap (ADR 0009): drives Google One Tap and its
 * fallback button, calling onCredential when GIS hands back a token.
 *
 * The hook reads VITE_GOOGLE_CLIENT_ID as a module-level constant, so tests
 * that exercise the "configured" path use `vi.resetModules()` + `vi.stubEnv`
 * to re-import the module with the env var set before each describe block.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act, waitFor, cleanup } from '@testing-library/react'

const REAL_CLIENT_ID = 'test-client-id.apps.googleusercontent.com'

// ---------------------------------------------------------------------------
// Factory: re-import useGoogleOneTap with a specific CLIENT_ID env.
// Must be called inside a test or beforeEach, after stubEnv + resetModules.
// ---------------------------------------------------------------------------
async function importWithClientId(clientId: string) {
  vi.resetModules()
  vi.stubEnv('VITE_GOOGLE_CLIENT_ID', clientId)

  // Re-mock googleIdentity after resetting modules.
  vi.doMock('./googleIdentity', () => ({
    getGoogleIdentity: vi.fn(),
    isOneTapDismissed: vi.fn(),
    loadGoogleScript: vi.fn(),
  }))

  // Import the mocked module FIRST so the doMock is fully registered before the
  // hook (which imports './googleIdentity' at module load) resolves. A concurrent
  // Promise.all import occasionally bound the REAL googleIdentity, whose
  // loadGoogleScript awaits a <script> onload that never fires in jsdom — hanging
  // the test until timeout. Sequential import closes that race window.
  const gi = await import('./googleIdentity')
  const { useGoogleOneTap } = await import('./useGoogleOneTap')

  return {
    useGoogleOneTap,
    getGsiMock: vi.mocked(gi.getGoogleIdentity),
    isDismissedMock: vi.mocked(gi.isOneTapDismissed),
    loadScriptMock: vi.mocked(gi.loadGoogleScript),
  }
}

function makeGsiApi() {
  return {
    initialize: vi.fn(),
    prompt: vi.fn(),
    renderButton: vi.fn(),
    cancel: vi.fn(),
    disableAutoSelect: vi.fn(),
  }
}

afterEach(() => {
  // Unmount any hook left mounted by the test so its pending init() promise
  // (which awaits loadGoogleScript) is cancelled and cannot leak state updates
  // into the next test's timing.
  cleanup()
  vi.unstubAllEnvs()
  vi.resetModules()
})

// ---------------------------------------------------------------------------
// Tests: unconfigured path (no CLIENT_ID)
// ---------------------------------------------------------------------------

describe('useGoogleOneTap — unconfigured (no client ID)', () => {
  it('reports unconfigured=true and does not load the GIS script', async () => {
    const { useGoogleOneTap, loadScriptMock } = await importWithClientId('')
    loadScriptMock.mockResolvedValue(undefined)

    const onCredential = vi.fn()
    const { result } = renderHook(() =>
      useGoogleOneTap({ onCredential, enabled: true }),
    )

    // Let effects settle — script should never be called.
    await act(async () => {})

    expect(result.current.unconfigured).toBe(true)
    expect(loadScriptMock).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// Tests: disabled path
// ---------------------------------------------------------------------------

describe('useGoogleOneTap — disabled', () => {
  it('does not load the GIS script when enabled=false', async () => {
    const { useGoogleOneTap, loadScriptMock } = await importWithClientId(REAL_CLIENT_ID)
    loadScriptMock.mockResolvedValue(undefined)

    const onCredential = vi.fn()
    const { result } = renderHook(() =>
      useGoogleOneTap({ onCredential, enabled: false }),
    )

    await act(async () => {})

    expect(loadScriptMock).not.toHaveBeenCalled()
    expect(result.current.showFallback).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Tests: script load failure
// ---------------------------------------------------------------------------

describe('useGoogleOneTap — script load failure', () => {
  it('sets showFallback=true when the GIS script fails to load', async () => {
    const { useGoogleOneTap, loadScriptMock } = await importWithClientId(REAL_CLIENT_ID)
    loadScriptMock.mockRejectedValue(new Error('network error'))

    const onCredential = vi.fn()
    const { result } = renderHook(() =>
      useGoogleOneTap({ onCredential, enabled: true }),
    )

    await waitFor(() => expect(result.current.showFallback).toBe(true))
  })
})

// ---------------------------------------------------------------------------
// Tests: GIS API unavailable after script loads
// ---------------------------------------------------------------------------

describe('useGoogleOneTap — GIS API unavailable after script load', () => {
  it('sets showFallback=true when getGoogleIdentity returns null', async () => {
    const { useGoogleOneTap, loadScriptMock, getGsiMock } = await importWithClientId(REAL_CLIENT_ID)
    loadScriptMock.mockResolvedValue(undefined)
    getGsiMock.mockReturnValue(null)

    const onCredential = vi.fn()
    const { result } = renderHook(() =>
      useGoogleOneTap({ onCredential, enabled: true }),
    )

    await waitFor(() => expect(result.current.showFallback).toBe(true))
  })
})

// ---------------------------------------------------------------------------
// Tests: One Tap prompt behavior
// ---------------------------------------------------------------------------

describe('useGoogleOneTap — One Tap prompt behavior', () => {
  it('initializes GIS and calls prompt when the script loads successfully', async () => {
    const { useGoogleOneTap, loadScriptMock, getGsiMock, isDismissedMock } =
      await importWithClientId(REAL_CLIENT_ID)

    loadScriptMock.mockResolvedValue(undefined)
    isDismissedMock.mockReturnValue(false)
    const gsi = makeGsiApi()
    getGsiMock.mockReturnValue(gsi)
    gsi.prompt.mockImplementation((cb) =>
      cb && cb({ isNotDisplayed: () => false, isSkippedMoment: () => false, isDismissedMoment: () => false }),
    )

    const onCredential = vi.fn()
    renderHook(() => useGoogleOneTap({ onCredential, enabled: true }))

    await waitFor(() => expect(gsi.initialize).toHaveBeenCalled())

    expect(gsi.initialize).toHaveBeenCalledWith(
      expect.objectContaining({ client_id: REAL_CLIENT_ID }),
    )
    expect(gsi.prompt).toHaveBeenCalled()
  })

  it('flips ready=true once the GIS script loads and the API is available', async () => {
    const { useGoogleOneTap, loadScriptMock, getGsiMock, isDismissedMock } =
      await importWithClientId(REAL_CLIENT_ID)

    loadScriptMock.mockResolvedValue(undefined)
    isDismissedMock.mockReturnValue(false)
    const gsi = makeGsiApi()
    getGsiMock.mockReturnValue(gsi)
    gsi.prompt.mockImplementation(() => {})

    const onCredential = vi.fn()
    const { result } = renderHook(() =>
      useGoogleOneTap({ onCredential, enabled: true }),
    )

    // Starts false (script not yet loaded), then flips true after init resolves.
    expect(result.current.ready).toBe(false)
    await waitFor(() => expect(result.current.ready).toBe(true))
  })

  it('does NOT re-initialize GIS on subsequent renders (initializedRef guard)', async () => {
    const { useGoogleOneTap, loadScriptMock, getGsiMock, isDismissedMock } =
      await importWithClientId(REAL_CLIENT_ID)

    loadScriptMock.mockResolvedValue(undefined)
    isDismissedMock.mockReturnValue(false)
    const gsi = makeGsiApi()
    getGsiMock.mockReturnValue(gsi)
    gsi.prompt.mockImplementation((cb) =>
      cb && cb({ isNotDisplayed: () => false, isSkippedMoment: () => false, isDismissedMoment: () => false }),
    )

    const onCredential = vi.fn()
    const { rerender } = renderHook(() =>
      useGoogleOneTap({ onCredential, enabled: true }),
    )

    await waitFor(() => expect(gsi.initialize).toHaveBeenCalledTimes(1))

    rerender()

    // initialize should still be called only once — the ref guards it.
    expect(gsi.initialize).toHaveBeenCalledTimes(1)
  })

  it('sets showFallback=true when One Tap is dismissed', async () => {
    const { useGoogleOneTap, loadScriptMock, getGsiMock, isDismissedMock } =
      await importWithClientId(REAL_CLIENT_ID)

    loadScriptMock.mockResolvedValue(undefined)
    const gsi = makeGsiApi()
    getGsiMock.mockReturnValue(gsi)
    // Simulate user dismissing One Tap.
    const fakeNote = {
      isNotDisplayed: () => false,
      isSkippedMoment: () => false,
      isDismissedMoment: () => true,
    }
    gsi.prompt.mockImplementation((cb) => cb && cb(fakeNote))
    isDismissedMock.mockReturnValue(true)

    const onCredential = vi.fn()
    const { result } = renderHook(() =>
      useGoogleOneTap({ onCredential, enabled: true }),
    )

    await waitFor(() => expect(result.current.showFallback).toBe(true))
  })

  it('passes the Google credential through to onCredential via the initialize callback', async () => {
    const { useGoogleOneTap, loadScriptMock, getGsiMock, isDismissedMock } =
      await importWithClientId(REAL_CLIENT_ID)

    loadScriptMock.mockResolvedValue(undefined)
    isDismissedMock.mockReturnValue(false)
    const gsi = makeGsiApi()
    getGsiMock.mockReturnValue(gsi)
    gsi.prompt.mockImplementation(() => {})

    let capturedCallback: ((response: { credential: string }) => void) | undefined
    gsi.initialize.mockImplementation((cfg: { callback: (r: { credential: string }) => void }) => {
      capturedCallback = cfg.callback
    })

    const onCredential = vi.fn()
    renderHook(() => useGoogleOneTap({ onCredential, enabled: true }))

    await waitFor(() => expect(capturedCallback).toBeDefined())

    // Simulate GIS delivering a credential token.
    act(() => {
      capturedCallback!({ credential: 'google-id-jwt' })
    })

    expect(onCredential).toHaveBeenCalledWith('google-id-jwt')
  })
})

// ---------------------------------------------------------------------------
// Tests: renderFallbackButton
// ---------------------------------------------------------------------------

describe('useGoogleOneTap — renderFallbackButton', () => {
  it('calls getGoogleIdentity().renderButton with the given element', async () => {
    const { useGoogleOneTap, getGsiMock, loadScriptMock } =
      await importWithClientId(REAL_CLIENT_ID)

    loadScriptMock.mockResolvedValue(undefined)
    const gsi = makeGsiApi()
    getGsiMock.mockReturnValue(gsi)

    const onCredential = vi.fn()
    const { result } = renderHook(() =>
      useGoogleOneTap({ onCredential, enabled: false }),
    )

    const el = document.createElement('div')
    act(() => {
      result.current.renderFallbackButton(el)
    })

    expect(gsi.renderButton).toHaveBeenCalledWith(
      el,
      expect.objectContaining({ type: 'standard' }),
    )
  })

  it('does nothing when passed null (element not yet mounted)', async () => {
    const { useGoogleOneTap, getGsiMock, loadScriptMock } =
      await importWithClientId(REAL_CLIENT_ID)

    loadScriptMock.mockResolvedValue(undefined)
    const gsi = makeGsiApi()
    getGsiMock.mockReturnValue(gsi)

    const onCredential = vi.fn()
    const { result } = renderHook(() =>
      useGoogleOneTap({ onCredential, enabled: false }),
    )

    act(() => {
      result.current.renderFallbackButton(null)
    })

    expect(gsi.renderButton).not.toHaveBeenCalled()
  })
})
