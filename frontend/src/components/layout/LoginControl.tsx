import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react'
import { LogOut } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { DemoBadge } from './DemoBadge'
import { getToastOptions } from '@/lib/toastOptions'
import { useAuth, useGoogleOneTap } from '@/state/auth'

/** Track a min-width media query so the Google button can pick its variant.
 * Backed by useSyncExternalStore (the canonical matchMedia binding) so there is
 * no setState-in-effect; falls back to desktop when matchMedia is unavailable
 * (SSR / jsdom). */
function useMinWidth(px: number): boolean {
  const query = `(min-width:${px}px)`
  const hasMM = () => typeof window !== 'undefined' && typeof window.matchMedia === 'function'
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (!hasMM()) return () => {}
      const mq = window.matchMedia(query)
      mq.addEventListener('change', onChange)
      return () => mq.removeEventListener('change', onChange)
    },
    [query],
  )
  const getSnapshot = () => (hasMM() ? window.matchMedia(query).matches : true)
  return useSyncExternalStore(subscribe, getSnapshot, () => true)
}

/**
 * Header auth control (ADR 0009): Google One Tap as primary login with a
 * fallback "Sign in with Google" button plus a "Try as guest" entry into the
 * read-only demo account, and a signed-in identity (with a demo badge) +
 * sign-out. Functional wiring only — the visual redesign is a later phase.
 */
export function LoginControl() {
  const { user, isLoading, isAuthenticated, isDemo, login, loginAsGuest, logout } = useAuth()

  const handleCredential = useCallback(
    (credential: string) => {
      login(credential).catch(() =>
        toast.error('登入失敗，請再試一次。', getToastOptions('error')),
      )
    },
    [login],
  )

  const { ready, renderFallbackButton, renderFallbackIconButton } = useGoogleOneTap({
    onCredential: handleCredential,
    enabled: !isLoading && !isAuthenticated,
  })

  // Always offer a Google sign-in affordance when logged out; One Tap, when it
  // shows, is an additive overlay — so logout never strands the user with only
  // "guest". Pick the variant by viewport (full official pill on desktop, a
  // compact icon below `sm` so the header never overflows) and render via an
  // effect since GIS's `renderButton` is imperative. Keyed on `ready` so a
  // late-loading GIS script still paints instead of silently no-opping, and
  // never into a display:none element (which rendered blank on mobile).
  const isDesktop = useMinWidth(640)
  const desktopBtnRef = useRef<HTMLDivElement>(null)
  const iconOverlayRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ready) return
    const el = isDesktop ? desktopBtnRef.current : iconOverlayRef.current
    if (!el) return
    el.innerHTML = '' // clear any prior render before switching variant
    if (isDesktop) renderFallbackButton(el)
    else renderFallbackIconButton(el)
  }, [ready, isDesktop, renderFallbackButton, renderFallbackIconButton])

  function handleLogout() {
    logout().catch(() =>
      toast.error('登出失敗，請再試一次。', getToastOptions('error')),
    )
  }

  function handleGuest() {
    loginAsGuest().catch(() =>
      toast.error('無法進入展示帳號，請稍後再試。', getToastOptions('error')),
    )
  }

  if (isLoading) {
    return <div className="h-8 w-24 animate-pulse rounded-md bg-muted" aria-hidden="true" />
  }

  if (isAuthenticated && user) {
    return (
      <div className="flex items-center gap-2">
        {isDemo && <DemoBadge />}
        {user.picture && (
          <img
            src={user.picture}
            alt=""
            referrerPolicy="no-referrer"
            className="h-7 w-7 rounded-full border border-border"
          />
        )}
        <span className="hidden text-sm font-medium sm:inline" title={user.email}>
          {user.name}
        </span>
        <Button variant="ghost" size="sm" onClick={handleLogout} aria-label="登出">
          <LogOut className="h-4 w-4" />
          <span className="hidden sm:inline">登出</span>
        </Button>
      </div>
    )
  }

  // Logged out: always offer Google sign-in (One Tap is additive) plus a
  // no-login "Try as guest" entry into the demo account.
  return (
    <div className="flex items-center gap-2 shrink-0">
      {isDesktop ? (
        // Desktop: Google's official "Sign in with Google" pill. Distinct `key`
        // from the mobile variant so React fully remounts on a breakpoint cross
        // instead of reusing this <div> — otherwise GIS's imperatively-injected
        // button (which React doesn't track) lingers as an orphan in the reused
        // node and bleeds into the other variant.
        <div key="google-desktop" ref={desktopBtnRef} aria-label="使用 Google 登入" className="shrink-0" />
      ) : (
        // Mobile: our own crisp Google "G" in a bordered square matching the
        // sibling buttons, with the (blank-rendering but still clickable) GIS
        // icon button stacked invisibly on top to capture the tap.
        <div
          key="google-mobile"
          className="relative inline-flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-md border border-input bg-background shadow-xs"
        >
          <GoogleGMark className="h-4 w-4" />
          <div
            ref={iconOverlayRef}
            aria-label="使用 Google 登入"
            className="absolute inset-0 cursor-pointer opacity-0"
          />
        </div>
      )}
      <Button variant="outline" size="sm" onClick={handleGuest} className="shrink-0">
        <span className="hidden sm:inline">以訪客身分試用</span>
        <span className="sm:hidden">訪客</span>
      </Button>
    </div>
  )
}

/** The official multicolour Google "G" mark, inlined so the compact mobile
 * sign-in button shows a crisp logo regardless of how GIS paints its icon. */
function GoogleGMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  )
}
