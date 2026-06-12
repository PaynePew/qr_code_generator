import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { LayoutDashboard, Loader2, ScanLine } from 'lucide-react'
import { useLinkList } from '@/state/linkEntry'
import { useAuth } from '@/state/auth'
import { getQrImageUrl, type LinkListItem } from '@/api/qr'
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

function LinkCard({ item }: { item: LinkListItem }) {
  const navigate = useNavigate()

  function handleCardClick(e: React.MouseEvent) {
    if ((e.target as HTMLElement).closest('button')) return
    navigate(`/dashboard/${item.token}`)
  }

  return (
    <div
      className="rounded-lg border bg-card p-4 shadow-xs flex gap-3 cursor-pointer hover:border-primary/40 hover:shadow-md transition-all"
      onClick={handleCardClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          navigate(`/dashboard/${item.token}`)
        }
      }}
      aria-label={`查看 ${item.label ?? item.token} 的詳情`}
    >
      {/* QR thumbnail — authoritative stored composite (bead 65g).
          Note: LinkListItem does not carry customization updated_at, so cache-bust
          is best-effort (no ?v= param); the browser's normal HTTP cache applies. */}
      <img
        src={getQrImageUrl(item.token)}
        alt={`QR 碼：${item.token}`}
        width={56}
        height={56}
        loading="lazy"
        className="rounded border border-border bg-white object-contain shrink-0 self-start"
      />

      <div className="flex flex-col gap-2 flex-1 min-w-0">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5 flex-1 min-w-0">
          {item.label && (
            <span className="text-sm font-semibold truncate" title={item.label}>
              {item.label}
            </span>
          )}
          <span
            className={[
              'truncate',
              item.label
                ? 'text-xs text-muted-foreground'
                : 'text-sm font-medium',
            ].join(' ')}
            title={item.original_url}
          >
            {truncateUrl(item.original_url)}
          </span>
        </div>
        <StatusBadge
          status={item.status}
          className={item.status === 'deleted' ? 'line-through' : undefined}
        />
      </div>

      <div className="flex items-center text-xs text-muted-foreground min-w-0">
        <span className="font-mono truncate">{item.short_url}</span>
        <CopyButton text={item.short_url} />
      </div>

      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span title={absoluteTime(item.created_at)}>建立於 {relativeTime(item.created_at)}</span>
        <span className="inline-flex items-center gap-1" title={`${item.scan_count} 次掃描`}>
          <ScanLine className="h-3 w-3" />
          {item.scan_count}
        </span>
      </div>
      </div>
    </div>
  )
}

export function Dashboard() {
  const [showTrash, setShowTrash] = useState(false)
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const list = useLinkList(showTrash, isAuthenticated)

  const items = list.data?.items ?? []
  // Logged out once auth has resolved, or the server rejected the session (401).
  const isUnauthenticated = (!authLoading && !isAuthenticated) || list.error?.status === 401
  // While auth is still resolving the list query is held (enabled=false), so
  // surface a loader rather than the empty state.
  const isLoading = authLoading || (isAuthenticated && list.isLoading)

  return (
    <div className="flex flex-col gap-4 max-w-2xl">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">儀表板</h1>
        {isAuthenticated && (
          <label className="flex items-center gap-1.5 text-sm cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showTrash}
              onChange={(e) => setShowTrash(e.target.checked)}
              className="cursor-pointer"
            />
            顯示已刪除
          </label>
        )}
      </div>

      {isUnauthenticated && (
        <div className="flex flex-col items-center gap-6 py-10 text-center">
          <div className="rounded-full bg-muted p-6">
            <LayoutDashboard className="h-12 w-12 text-muted-foreground/60" />
          </div>
          <div className="flex flex-col gap-2">
            <h2 className="text-xl font-semibold">請先登入</h2>
            <p className="text-sm text-muted-foreground max-w-sm">
              登入後即可在任何裝置上看到你建立的所有連結與掃描數據。
            </p>
          </div>
        </div>
      )}

      {!isUnauthenticated && isLoading && (
        <div className="flex items-center gap-2 text-muted-foreground text-sm py-10">
          <Loader2 className="h-4 w-4 animate-spin" />
          載入連結…
        </div>
      )}

      {!isUnauthenticated && list.isError && list.error.status !== 401 && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          無法載入連結，請稍後再試。
        </div>
      )}

      {!isUnauthenticated && !isLoading && list.isSuccess && items.length > 0 && (
        <>
          <p className="text-sm text-muted-foreground">
            {showTrash ? '包含已刪除的連結' : '你建立的連結'}（共 {items.length} 筆），依建立時間由新至舊排列。
          </p>
          <div className="flex flex-col gap-3">
            {items.map((item) => (
              <LinkCard key={item.token} item={item} />
            ))}
          </div>
        </>
      )}

      {!isUnauthenticated && !isLoading && list.isSuccess && items.length === 0 && (
        <div className="flex flex-col items-center gap-6 py-10 text-center">
          <div className="rounded-full bg-muted p-6">
            <LayoutDashboard className="h-12 w-12 text-muted-foreground/60" />
          </div>
          <div className="flex flex-col gap-2">
            <h2 className="text-xl font-semibold">
              {showTrash ? '沒有已刪除的連結' : '還沒有任何連結'}
            </h2>
            <p className="text-sm text-muted-foreground max-w-sm">
              {showTrash
                ? '刪除連結後會出現在這裡。'
                : '你的連結會跨裝置同步，登入後在任何瀏覽器都看得到。'}
            </p>
          </div>
          {!showTrash && (
            <Link to="/">
              <Button>建立第一個 QR Code</Button>
            </Link>
          )}
        </div>
      )}
    </div>
  )
}
