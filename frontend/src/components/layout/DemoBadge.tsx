import { Eye } from 'lucide-react'

/**
 * Unmistakable "Demo · read-only" badge (ADR 0009). It must read as read-only,
 * never as "this feature isn't built" — so a first-time visitor (interviewer)
 * knows mutations are intentionally blocked. Shown whenever the signed-in User
 * is the shared demo account.
 */
export function DemoBadge() {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800"
      role="status"
      aria-label="展示帳號，唯讀模式"
      title="這是唯讀的展示帳號。登入即可建立並管理你自己的 QR 碼。"
    >
      <Eye className="h-3 w-3" aria-hidden="true" />
      展示 · 唯讀
    </span>
  )
}
