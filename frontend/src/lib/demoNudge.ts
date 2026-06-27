import { toast } from 'sonner'
import { isDemoReadOnly } from '@/api/auth'
import type { ApiError } from '@/api/client'
import { getToastOptions } from './toastOptions'

/**
 * Convert a read-only demo rejection into a friendly "log in to create" nudge
 * (ADR 0009): a guest who tries to create/edit/delete should be guided toward
 * signing in, never shown a raw 403.
 *
 * Returns `true` when the error was the demo guard (and the nudge was shown), so
 * a mutation's error handler can early-return; `false` for any other error,
 * leaving the caller's normal error handling in charge.
 */
export function nudgeIfDemoReadOnly(err: ApiError | null | undefined): boolean {
  if (!isDemoReadOnly(err)) return false
  toast.info('此為展示帳號，請登入後操作', getToastOptions('warning'))
  return true
}

/**
 * Convert a 401 (no/expired session — the visitor is neither a guest nor signed
 * in) into a friendly "try as guest or sign in" nudge instead of a scary
 * "network error" toast. Anonymous visitors who click create before signing in
 * should be guided, not alarmed (ADR 0009 — login required to create).
 *
 * Returns `true` when the error was the unauthenticated guard (and the nudge was
 * shown), so a mutation's error handler can early-return.
 */
export function nudgeIfUnauthenticated(err: ApiError | null | undefined): boolean {
  if (err?.status !== 401) return false
  toast.info('請以訪客身分開啟唯讀模式，或登入 Google 後開始使用。', getToastOptions('warning'))
  return true
}
