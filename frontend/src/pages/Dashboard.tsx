import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, Link } from 'react-router-dom'
import { LayoutDashboard, Loader2 } from 'lucide-react'
import { listTokens, removeFromHistory, addToken, type HistoryEntry } from '@/state/linkHistory'
import { getLink, type GetLinkResponse } from '@/api/qr'
import { linkKey } from '@/api/queryKeys'
import type { ApiError } from '@/api/client'
import { CopyButton } from '@/components/ui/CopyButton'
import { StatusBadge, type DerivedStatus } from '@/components/ui/StatusBadge'
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

function RecoverByToken({ onRecovered }: { onRecovered: () => void }) {
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isPending, setIsPending] = useState(false)

  async function handleRecover() {
    const t = token.trim()
    if (!t) return
    setError(null)
    setIsPending(true)
    try {
      const data = await getLink(t)
      addToken({
        token: data.token,
        originalUrl: data.original_url,
        createdAt: data.created_at,
      })
      setToken('')
      onRecovered()
    } catch (err) {
      const apiError = err as ApiError
      if (apiError.status === 404) {
        setError('找不到此 Token，請確認後再試。')
      } else {
        setError('發生錯誤，請稍後再試。')
      }
    } finally {
      setIsPending(false)
    }
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
          onKeyDown={(e) => { if (e.key === 'Enter') void handleRecover() }}
          disabled={isPending}
          className="flex-1 rounded-md border border-input px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-50"
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void handleRecover()}
          disabled={isPending || !token.trim()}
        >
          {isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : '還原'}
        </Button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

function LinkCard({
  entry,
  hideDeleted,
  onRemove,
}: {
  entry: HistoryEntry
  hideDeleted: boolean
  onRemove: (token: string) => void
}) {
  const navigate = useNavigate()
  const query = useQuery<GetLinkResponse, ApiError>({
    queryKey: linkKey(entry.token),
    queryFn: () => getLink(entry.token),
    retry: (_count, error) => error.status !== 404,
  })

  let status: DerivedStatus = 'active'
  if (query.isError && query.error.status === 404) {
    status = 'missing'
  } else if (query.data) {
    status = query.data.status
  } else if (entry.dismissed) {
    status = 'deleted'
  }

  // Catches API-reported deleted even when local dismissed flag is stale
  if (hideDeleted && status === 'deleted') return null

  const shortUrl = query.data?.short_url ?? `…/r/${entry.token}`
  const showRemoveButton = status === 'deleted' || status === 'missing'

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
        <span className="text-sm font-medium truncate max-w-xs" title={entry.originalUrl}>
          {truncateUrl(entry.originalUrl)}
        </span>
        {query.isLoading ? (
          <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground animate-pulse">
            載入中
          </span>
        ) : (
          <StatusBadge status={status} className={status === 'deleted' ? 'line-through' : undefined} />
        )}
      </div>

      <div className="flex items-center text-xs text-muted-foreground">
        <span className="font-mono">{shortUrl}</span>
        <CopyButton text={shortUrl} />
      </div>

      <div className="text-xs text-muted-foreground" title={absoluteTime(entry.createdAt)}>
        建立於 {relativeTime(entry.createdAt)}
      </div>

      {showRemoveButton && (
        <button
          type="button"
          className="self-start mt-1 text-xs text-muted-foreground underline underline-offset-2 hover:text-destructive transition-colors"
          onClick={(e) => {
            e.stopPropagation()
            onRemove(entry.token)
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
  const [entries, setEntries] = useState(() => listTokens())

  const refreshEntries = useCallback(() => {
    setEntries(listTokens())
  }, [])

  function handleRemove(token: string) {
    removeFromHistory(token)
    refreshEntries()
  }

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
            {visibleEntries.map((entry) => (
              <LinkCard
                key={entry.token}
                entry={entry}
                hideDeleted={hideDeleted}
                onRemove={handleRemove}
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
            <RecoverByToken onRecovered={refreshEntries} />
          </div>
        </div>
      )}
    </div>
  )
}
