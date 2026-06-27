import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getGoogleIdentity,
  isOneTapDismissed,
  loadGoogleScript,
  type GoogleButtonConfig,
  type GoogleCredentialResponse,
} from './googleIdentity'

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? ''

const FALLBACK_BUTTON_CONFIG: GoogleButtonConfig = {
  type: 'standard',
  theme: 'outline',
  size: 'large',
  text: 'signin_with',
  shape: 'pill',
}

// Compact icon-only variant for narrow viewports — the full "Sign in with
// Google" pill is ~200px and overflows the header on mobile (RWD fix). GIS's
// icon button paints blank in this header, so the caller stacks it at opacity 0
// over its own Google "G" mark and only uses it to capture the click — the
// theme/shape are therefore invisible; we keep `large` for a generous hit area.
const ICON_BUTTON_CONFIG: GoogleButtonConfig = {
  type: 'icon',
  theme: 'outline',
  size: 'large',
  shape: 'square',
}

export interface UseGoogleOneTapOptions {
  /** Trade the One Tap credential for an app session. */
  onCredential: (credential: string) => void
  /** Skip One Tap entirely (e.g. already signed in). */
  enabled: boolean
}

export interface UseGoogleOneTapResult {
  /** True once One Tap was not shown/skipped/dismissed — render the fallback button. */
  showFallback: boolean
  /** True when no Google client id is configured — the whole feature is unavailable. */
  unconfigured: boolean
  /** True once the GIS script is loaded and `renderButton` can actually paint.
   * Callers key their render effect on this so a late-loading script still
   * paints instead of silently no-opping on the first commit. */
  ready: boolean
  /** Ref-callback that renders Google's official full "Sign in with Google" button. */
  renderFallbackButton: (element: HTMLElement | null) => void
  /** Ref-callback that renders the compact icon-only button (narrow viewports). */
  renderFallbackIconButton: (element: HTMLElement | null) => void
}

/**
 * Drive Google One Tap and its fallback button (ADR 0009).
 *
 * One Tap is primary; when the browser/policy/user prevents it from showing we
 * surface `showFallback` so the caller can mount the explicit "Sign in with
 * Google" button. The Google ID token from either path is handed to
 * `onCredential`, which the app verifies server-side to start its own session.
 */
export function useGoogleOneTap({
  onCredential,
  enabled,
}: UseGoogleOneTapOptions): UseGoogleOneTapResult {
  const [showFallback, setShowFallback] = useState(false)
  const [ready, setReady] = useState(false)
  const initializedRef = useRef(false)
  // Keep the latest callback without re-running the init effect on every render.
  // Write the ref in an effect (not during render) so render stays pure — the GIS
  // callback reads `.current` only on user auth, long after commit, so the
  // post-commit update is always in time (react-hooks/refs, plugin v6).
  const onCredentialRef = useRef(onCredential)
  useEffect(() => {
    onCredentialRef.current = onCredential
  })

  const unconfigured = CLIENT_ID === ''

  useEffect(() => {
    if (!enabled || unconfigured) return
    let cancelled = false

    async function init() {
      try {
        await loadGoogleScript()
      } catch {
        if (!cancelled) setShowFallback(true)
        return
      }
      if (cancelled) return

      const gsi = getGoogleIdentity()
      if (!gsi) {
        setShowFallback(true)
        return
      }

      // GIS is live — let the caller paint the official button now.
      setReady(true)

      if (!initializedRef.current) {
        gsi.initialize({
          client_id: CLIENT_ID,
          callback: (response: GoogleCredentialResponse) =>
            onCredentialRef.current(response.credential),
          cancel_on_tap_outside: false,
        })
        initializedRef.current = true
      }

      gsi.prompt((notification) => {
        if (isOneTapDismissed(notification)) setShowFallback(true)
      })
    }

    void init()
    return () => {
      cancelled = true
    }
  }, [enabled, unconfigured])

  const renderFallbackButton = useCallback((element: HTMLElement | null) => {
    if (!element) return
    getGoogleIdentity()?.renderButton(element, FALLBACK_BUTTON_CONFIG)
  }, [])

  const renderFallbackIconButton = useCallback((element: HTMLElement | null) => {
    if (!element) return
    getGoogleIdentity()?.renderButton(element, ICON_BUTTON_CONFIG)
  }, [])

  return { showFallback, unconfigured, ready, renderFallbackButton, renderFallbackIconButton }
}
