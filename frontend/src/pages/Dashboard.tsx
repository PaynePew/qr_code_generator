import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { LayoutDashboard, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  useLinkHistory,
  useLinkEntry,
  useRecoverEntry,
  type HistoryEntry,
} from '@/state/linkEntry'
import { computeExpiresAt, toDatetimeLocalValue } from '@/lib/expiresAtPresets'
import { getToastOptions } from '@/lib/toastOptions'
import { CopyButton } from '@/components/ui/CopyButton'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { Button } from '@/components/ui/button'

const rtf = new Intl.RelativeTimeFormat('zh-TW', { numeric: 'auto' })
const dtf = new Intl.DateTimeFormat('zh-TW', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

function relativeTime(isoDate: string): string {
  const diffMs = new Date(isoDate).getTime() - Date.now()
  const abs = Math.abs(diffMs)

  if (abs < 60_000) return rtf.format(Math.round(diffMs / 1_000), 'second')
  if (abs < 3_600_000) return rtf.format(Math.round(diffMs / 60_000), 'minute')
  if (abs < 86_400_000) return rtf.format(Math.round(diffMs / 3_600_000), 'hour')
  return rtf.format(Math.round(diffMs / 86_400_000), 'day')
}

function absoluteTime(isoDate: string): string {
  return dtf.format(new Date(isoDate))
}

function truncateUrl(url: string, max = 50): string {
  if (url.length <= max) return url
  return url.slice(0, max) + '…'
}

function RecoverByToken() {
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  const recover = useRecoverEntry()

  function handleRecover() {
    const t = token.trim()
    if (!t) return
    setError(null)
    recover.mutate(t, {
      onSuccess() {
        setToken('')
      },
      onError(err) {
        if (err.status === 404) {
          setError('找不到此 Token，請確認後再試。')
        } else {
          setError('發生錯誤，請稍後再試。')
        }
      },
    })
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm font-medium text-muted-foreground">以 Token 還原</p>
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="輸入 Token…"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleRecover() }}
          disabled={recover.isPending}
          className="flex-1 rounded-md border border-input px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-50"
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleRecover}
          disabled={recover.isPending || !token.trim()}
        >
          {recover.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : '還原'}
        </Button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

function LinkCard({
  row,
  hideDeleted,
}: {
  row: HistoryEntry
  hideDeleted: boolean
}) {
  const navigate = useNavigate()
  const entry = useLinkEntry(row.token, row)

  // Catches API-reported deleted even when local dismissed flag is stale
  if (hideDeleted && entry.status === 'deleted') return null

  const shortUrl = entry.link?.short_url ?? `…/r/${entry.token}`
  const showRemoveButton = entry.status === 'deleted' || entry.status === 'missing'

  const [showReactivate, setShowReactivate] = useState(false)
  const [reactivateDate, setReactivateDate] = useState<string>(() =>
    toDatetimeLocalValue(new Date(computeExpiresAt(new Date(), '+30d')!)),
  )

  async function handleReactivate() {
    try {
      await entry.reactivate(new Date(reactivateDate).toISOString())
      setShowReactivate(false)
      toast.success('連結已重新啟用', getToastOptions('success'))
    } catch {
      toast.error('重新啟用失敗，請稍後再試。', getToastOptions('error'))
    }
  }

  function handleCardClick(e: React.MouseEvent) {
    if ((e.target as HTMLElement).closest('button')) return
    navigate(`/dashboard/${entry.token}`)
  }

  return (
    <div
      className="rounded-lg border bg-card p-4 shadow-sm flex flex-col gap-2 cursor-pointer hover:border-primary/40 hover:shadow-md transition-all"
      onClick={handleCardClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          navigate(`/dashboard/${entry.token}`)
        }
      }}
      aria-label={`查看 ${entry.token} 的詳情`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium truncate flex-1 min-w-0" title={entry.originalUrl}>
          {truncateUrl(entry.originalUrl)}
        </span>
        {entry.isLoading ? (
          <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground animate-pulse">
            載入中
          </span>
        ) : (
          <StatusBadge status={entry.status} className={entry.status === 'deleted' ? 'line-through' : undefined} />
        )}
      </div>

      <div className="flex items-center text-xs text-muted-foreground min-w-0">
        <span className="font-mono truncate">{shortUrl}</span>
        <CopyButton text={shortUrl} />
      </div>

      <div className="text-xs text-muted-foreground" title={absoluteTime(entry.createdAt)}>
        建立於 {relativeTime(entry.createdAt)}
      </div>

      {entry.status === 'expired' && !showReactivate && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); setShowReactivate(true) }}
          className="self-start mt-1 rounded-md border border-amber-400 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700 hover:bg-amber-100 transition-colors"
        >
          重新啟用
        </button>
      )}

      {entry.status === 'expired' && showReactivate && (
        <div
          className="flex flex-col gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 mt-1"
          onClick={(e) => e.stopPropagation()}
        >
          <label className="text-xs font-medium text-amber-800">選擇新的到期時間</label>
          <input
            type="datetime-local"
            value={reactivateDate}
            onChange={(e) => setReactivateDate(e.target.value)}
            disabled={entry.reactivate.isPending}
            className="rounded-md border border-amber-300 px-3 py-1.5 text-xs outline-none focus:ring-2 focus:ring-amber-400/50 bg-white disabled:opacity-50"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleReactivate}
              disabled={entry.reactivate.isPending || !reactivateDate}
              className="flex items-center gap-1 rounded-md bg-amber-500 px-3 py-1 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-50 transition-colors"
            >
              {entry.reactivate.isPending ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" />
                  啟用中…
                </>
              ) : (
                '確認啟用'
              )}
            </button>
            <button
              type="button"
              onClick={() => setShowReactivate(false)}
              disabled={entry.reactivate.isPending}
              className="rounded-md border border-amber-300 px-3 py-1 text-xs font-medium text-amber-700 hover:bg-amber-100 disabled:opacity-50 transition-colors"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {showRemoveButton && (
        <button
          type="button"
          className="self-start mt-1 text-xs text-muted-foreground underline underline-offset-2 hover:text-destructive transition-colors"
          onClick={(e) => {
            e.stopPropagation()
            entry.removeFromHistory()
          }}
        >
          從歷史紀錄移除
        </button>
      )}
    </div>
  )
}

export function Dashboard() {
  const [hideDeleted, setHideDeleted] = useState(true)
  const entries = useLinkHistory()

  // Fast-path filter by local dismissed flag; LinkCard handles API-reported deleted
  const visibleEntries = hideDeleted ? entries.filter((e) => !e.dismissed) : entries
  const showEmpty = visibleEntries.length === 0

  return (
    <div className="flex flex-col gap-4 max-w-2xl">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">儀表板</h1>
        {entries.length > 0 && (
          <label className="flex items-center gap-1.5 text-sm cursor-pointer select-none">
            <input
              type="checkbox"
              checked={hideDeleted}
              onChange={(e) => setHideDeleted(e.target.checked)}
              className="cursor-pointer"
            />
            隱藏已刪除
          </label>
        )}
      </div>

      {!showEmpty && (
        <>
          <p className="text-sm text-muted-foreground">
            顯示此瀏覽器建立的連結（共 {entries.length} 筆），依建立時間由新至舊排列。
          </p>
          <div className="flex flex-col gap-3">
            {visibleEntries.map((row) => (
              <LinkCard
                key={row.token}
                row={row}
                hideDeleted={hideDeleted}
              />
            ))}
          </div>
        </>
      )}

      {showEmpty && (
        <div className="flex flex-col items-center gap-6 py-10 text-center">
          <div className="rounded-full bg-muted p-6">
            <LayoutDashboard className="h-12 w-12 text-muted-foreground/60" />
          </div>
          <div className="flex flex-col gap-2">
            <h2 className="text-xl font-semibold">還沒有任何連結</h2>
            <p className="text-sm text-muted-foreground max-w-sm">
              連結記錄僅儲存於此瀏覽器的本機儲存空間，其他裝置或瀏覽器無法存取。清除瀏覽器資料會同時移除所有記錄。
            </p>
          </div>
          <Link to="/">
            <Button>建立第一個 QR Code</Button>
          </Link>
          <div className="w-full max-w-sm border-t pt-4">
            <RecoverByToken />
          </div>
        </div>
      )}
    </div>
  )
}
