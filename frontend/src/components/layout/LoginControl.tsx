import { useCallback } from 'react'
import { LogOut } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { DemoBadge } from './DemoBadge'
import { getToastOptions } from '@/lib/toastOptions'
import { useAuth, useGoogleOneTap } from '@/state/auth'

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

  const { showFallback, unconfigured, renderFallbackButton } = useGoogleOneTap({
    onCredential: handleCredential,
    enabled: !isLoading && !isAuthenticated,
  })

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

  // Logged out: One Tap drives login; show the fallback button when it cannot,
  // and always offer a no-login "Try as guest" entry into the demo account.
  return (
    <div className="flex items-center gap-2">
      {(showFallback || unconfigured) && (
        <div ref={renderFallbackButton} aria-label="使用 Google 登入" />
      )}
      <Button variant="outline" size="sm" onClick={handleGuest}>
        以訪客身分試用
      </Button>
    </div>
  )
}
