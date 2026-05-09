import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { listTokens, type HistoryEntry } from '@/state/linkHistory'
import { getLink, patchLink, type GetLinkResponse } from '@/api/qr'
import { linkKey } from '@/api/queryKeys'
import type { ApiError } from '@/api/client'
import { computeExpiresAt, toDatetimeLocalValue } from '@/lib/expiresAtPresets'
import { getToastOptions } from '@/lib/toastOptions'
import { CopyButton } from '@/components/ui/CopyButton'
import { StatusBadge, type DerivedStatus } from '@/components/ui/StatusBadge'

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

function LinkCard({ entry }: { entry: HistoryEntry }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const query = useQuery<GetLinkResponse, ApiError>({
    queryKey: linkKey(entry.token),
    queryFn: () => getLink(entry.token),
    retry: (_count, error) => error.status !== 404,
  })

  const status: DerivedStatus =
    query.isError && query.error.status === 404
      ? 'missing'
      : (query.data?.status ?? 'active')

  const shortUrl = query.data?.short_url ?? `…/r/${entry.token}`

  const [showReactivate, setShowReactivate] = useState(false)
  const [reactivateDate, setReactivateDate] = useState<string>(() =>
    toDatetimeLocalValue(new Date(computeExpiresAt(new Date(), '+30d')!)),
  )

  const reactivateMutation = useMutation<GetLinkResponse, ApiError, string>({
    mutationFn: (expires_at) => patchLink(entry.token, { expires_at }),
    onSuccess(data) {
      queryClient.setQueryData(linkKey(entry.token), data)
      queryClient.invalidateQueries({ queryKey: ['link', entry.token] })
      setShowReactivate(false)
      toast.success('連結已重新啟用', getToastOptions('success'))
    },
    onError() {
      toast.error('重新啟用失敗，請稍後再試。', getToastOptions('error'))
    },
  })

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
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/dashboard/${entry.token}`) } }}
      aria-label={`查看 ${entry.token} 的詳情`}
    >
      <div className="flex items-start justify-between gap-2">
        <span
          className="text-sm font-medium truncate max-w-xs"
          title={entry.originalUrl}
        >
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

      {/* Reactivate button for expired cards */}
      {status === 'expired' && !showReactivate && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); setShowReactivate(true) }}
          className="self-start mt-1 rounded-md border border-amber-400 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700 hover:bg-amber-100 transition-colors"
        >
          重新啟用
        </button>
      )}

      {status === 'expired' && showReactivate && (
        <div
          className="flex flex-col gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 mt-1"
          onClick={(e) => e.stopPropagation()}
        >
          <label className="text-xs font-medium text-amber-800">選擇新的到期時間</label>
          <input
            type="datetime-local"
            value={reactivateDate}
            onChange={(e) => setReactivateDate(e.target.value)}
            disabled={reactivateMutation.isPending}
            className="rounded-md border border-amber-300 px-3 py-1.5 text-xs outline-none focus:ring-2 focus:ring-amber-400/50 bg-white disabled:opacity-50"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => reactivateMutation.mutate(new Date(reactivateDate).toISOString())}
              disabled={reactivateMutation.isPending || !reactivateDate}
              className="flex items-center gap-1 rounded-md bg-amber-500 px-3 py-1 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-50 transition-colors"
            >
              {reactivateMutation.isPending ? (
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
              disabled={reactivateMutation.isPending}
              className="rounded-md border border-amber-300 px-3 py-1 text-xs font-medium text-amber-700 hover:bg-amber-100 disabled:opacity-50 transition-colors"
            >
              取消
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export function Dashboard() {
  const entries = listTokens()

  if (entries.length === 0) {
    return (
      <div className="flex flex-col gap-4 max-w-2xl">
        <h1 className="text-2xl font-bold">儀表板</h1>
        <p className="text-muted-foreground">
          您在此瀏覽器建立的所有短網址連結將顯示於此。
        </p>
        <div className="rounded-md border bg-muted p-6 text-center">
          <p className="text-sm font-medium mb-1">尚無連結記錄</p>
          <p className="text-xs text-muted-foreground">
            連結記錄儲存於此瀏覽器，其他裝置無法存取。請至「產生器」頁面建立您的第一個 QR 碼連結。
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 max-w-2xl">
      <h1 className="text-2xl font-bold">儀表板</h1>
      <p className="text-muted-foreground">
        顯示此瀏覽器建立的連結（共 {entries.length} 筆），依建立時間由新至舊排列。
      </p>
      <div className="flex flex-col gap-3">
        {entries.map((entry) => (
          <LinkCard key={entry.token} entry={entry} />
        ))}
      </div>
    </div>
  )
}
