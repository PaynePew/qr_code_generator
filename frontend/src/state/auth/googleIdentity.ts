/**
 * Framework-free glue around Google Identity Services (GIS).
 *
 * GIS returns a Google-signed ID token to a callback; the app then trades it for
 * its own session (ADR 0009 — Google's token is never the session). Keeping the
 * script-loading and the "did One Tap actually show?" decision here, away from
 * React, makes both unit-testable.
 */

/** A One Tap credential the GIS callback hands back (the Google ID token JWT). */
export interface GoogleCredentialResponse {
  credential: string
}

/** The moment notification GIS passes to `prompt`'s listener. */
export interface GoogleNotification {
  isNotDisplayed: () => boolean
  isSkippedMoment: () => boolean
  isDismissedMoment: () => boolean
}

export interface GoogleInitializeConfig {
  client_id: string
  callback: (response: GoogleCredentialResponse) => void
  auto_select?: boolean
  cancel_on_tap_outside?: boolean
}

export interface GoogleButtonConfig {
  type?: 'standard' | 'icon'
  theme?: 'outline' | 'filled_blue' | 'filled_black'
  size?: 'small' | 'medium' | 'large'
  text?: 'signin_with' | 'signup_with' | 'continue_with' | 'signin'
  shape?: 'rectangular' | 'pill' | 'circle' | 'square'
  width?: number
}

/** The slice of `window.google.accounts.id` this app uses. */
export interface GoogleIdentityApi {
  initialize: (config: GoogleInitializeConfig) => void
  prompt: (listener?: (notification: GoogleNotification) => void) => void
  renderButton: (parent: HTMLElement, config: GoogleButtonConfig) => void
  cancel: () => void
  disableAutoSelect: () => void
}

export const GOOGLE_GSI_SRC = 'https://accounts.google.com/gsi/client'

/** Resolve the live GIS API if the script has loaded, else null. */
export function getGoogleIdentity(): GoogleIdentityApi | null {
  return window.google?.accounts?.id ?? null
}

/**
 * Whether One Tap failed to display (not shown, skipped, or dismissed) — the
 * cue to fall back to the explicit "Sign in with Google" button.
 */
export function isOneTapDismissed(notification: GoogleNotification): boolean {
  return (
    notification.isNotDisplayed() ||
    notification.isSkippedMoment() ||
    notification.isDismissedMoment()
  )
}

/**
 * Inject the GIS client script once. Resolves when it is ready (or already
 * present); rejects if it fails to load.
 */
export function loadGoogleScript(doc: Document = document): Promise<void> {
  if (doc.querySelector(`script[src="${GOOGLE_GSI_SRC}"]`)) {
    return Promise.resolve()
  }
  return new Promise<void>((resolve, reject) => {
    const script = doc.createElement('script')
    script.src = GOOGLE_GSI_SRC
    script.async = true
    script.defer = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load Google Identity Services script'))
    doc.head.appendChild(script)
  })
}
