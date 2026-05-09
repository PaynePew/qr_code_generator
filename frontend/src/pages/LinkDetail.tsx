import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from '@tanstack/react-form'
import { toast } from 'sonner'
import { ArrowLeft, Loader2, Trash2, Pencil } from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { format, subDays, parseISO } from 'date-fns'
import { getLink, patchLink, deleteLink, getAnalytics, type GetLinkResponse, type AnalyticsResponse } from '@/api/qr'
import { linkKey, analyticsKey } from '@/api/queryKeys'
import type { ApiError } from '@/api/client'
import { urlSchema } from '@/schemas/url'
import { cn } from '@/lib/utils'
import { getStyle } from '@/state/styleStore'
import { create as createRenderer, type QRRenderer } from '@/qr/renderer'
import { markDeleted } from '@/state/linkHistory'
import { getToastOptions } from '@/lib/toastOptions'
import { Button } from '@/components/ui/button'
import { CopyButton } from '@/components/ui/CopyButton'
import { StatusBadge, type DerivedStatus } from '@/components/ui/StatusBadge'
import { parse as parseUA } from '@/lib/uaParser'

const BASE_URL = import.meta.env.VITE_BASE_URL ?? window.location.origin

const dtf = new Intl.DateTimeFormat('zh-TW', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

const relDtf = new Intl.RelativeTimeFormat('zh-TW', { numeric: 'auto' })

function relativeTime(isoDate: string): string {
  const diff = (new Date(isoDate).getTime() - Date.now()) / 1000
  if (Math.abs(diff) < 60) return relDtf.format(Math.round(diff), 'second')
  if (Math.abs(diff) < 3600) return relDtf.format(Math.round(diff / 60), 'minute')
  if (Math.abs(diff) < 86400) return relDtf.format(Math.round(diff / 3600), 'hour')
  return relDtf.format(Math.round(diff / 86400), 'day')
}

type ChartFilter = 'all' | '302' | '410'

const CHART_LINE_CONFIG: Record<ChartFilter, { dataKey: string; stroke: string; name: string }> = {
  all: { dataKey: 'all', stroke: '#22c55e', name: '全部' },
  '302': { dataKey: '302', stroke: '#22c55e', name: '302' },
  '410': { dataKey: '410', stroke: '#ef4444', name: '410' },
}

interface ChartPoint {
  date: string
  all: number
  '302': number
  '410': number
}

function buildChartData(analytics: AnalyticsResponse): ChartPoint[] {
  const today = new Date()
  const byDate: Record<string, ChartPoint> = {}

  for (let i = 29; i >= 0; i--) {
    const d = format(subDays(today, i), 'yyyy-MM-dd')
    byDate[d] = { date: d, all: 0, '302': 0, '410': 0 }
  }

  for (const day of analytics.scans_by_day) {
    if (byDate[day.date]) {
      byDate[day.date].all = day.count
      byDate[day.date]['302'] = day.status_codes['302'] ?? 0
      byDate[day.date]['410'] = day.status_codes['410'] ?? 0
    }
  }

  return Object.values(byDate)
}

function formatChartDate(dateStr: string): string {
  try {
    return format(parseISO(dateStr), 'MM/dd')
  } catch {
    return dateStr
  }
}

function statusBadgeClass(code: number): string {
  return code === 302
    ? 'bg-green-100 text-green-800'
    : 'bg-red-100 text-red-800'
}

function formatUa(rawUa: string | null): string {
  if (!rawUa) return '未知'
  const { browser, os } = parseUA(rawUa)
  if (browser && os) return `${browser} on ${os}`
  if (browser) return browser
  if (os) return os
  return rawUa.slice(0, 40)
}

function todayScans(analytics: AnalyticsResponse): number {
  const today = format(new Date(), 'yyyy-MM-dd')
  return analytics.scans_by_day.find((d) => d.date === today)?.count ?? 0
}

function successRate(analytics: AnalyticsResponse): string {
  const total = analytics.total_scans
  if (total === 0) return '—'
  const success = analytics.scans_by_day.reduce((acc, d) => acc + (d.status_codes['302'] ?? 0), 0)
  return `${Math.round((success / total) * 100)}%`
}

function AnalyticsSection({ token }: { token: string }) {
  const [filter, setFilter] = useState<ChartFilter>('all')

  const query = useQuery<AnalyticsResponse, ApiError>({
    queryKey: analyticsKey(token),
    queryFn: () => getAnalytics(token),
    enabled: !!token,
  })

  if (query.isLoading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground text-sm py-4">
        <Loader2 className="h-4 w-4 animate-spin" />
        載入分析資料…
      </div>
    )
  }

  if (query.isError) {
    return (
      <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
        無法載入分析資料，請稍後再試。
      </div>
    )
  }

  const analytics = query.data!
  const chartData = buildChartData(analytics)
  const today = todayScans(analytics)
  const rate = successRate(analytics)

  if (analytics.total_scans === 0) {
    return (
      <div className="rounded-lg border bg-muted/30 p-6 text-center text-sm text-muted-foreground">
        尚無掃描紀錄 — 將你的 QR Code 印出來/分享出去，回來這裡看數據！
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5">
      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {[
          { label: '總掃描次數', value: analytics.total_scans },
          { label: '今日掃描', value: today },
          { label: '成功率', value: rate },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-lg border bg-card p-4 flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">{label}</span>
            <span className="text-2xl font-bold">{value}</span>
          </div>
        ))}
      </div>

      {/* Line chart */}
      <div className="rounded-lg border bg-card p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <span className="text-sm font-medium">過去 30 天掃描趨勢</span>
          <div className="flex gap-1">
            {(['all', '302', '410'] as ChartFilter[]).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={cn(
                  'px-2 py-1 rounded text-xs font-medium transition-colors',
                  filter === f
                    ? 'bg-primary text-primary-foreground'
                    : 'border border-input hover:bg-muted',
                )}
              >
                {f === 'all' ? '全部' : f}
              </button>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis
              dataKey="date"
              tickFormatter={formatChartDate}
              tick={{ fontSize: 11 }}
              interval="preserveStartEnd"
            />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip
              labelFormatter={(v) => formatChartDate(String(v))}
              formatter={(value, name) => [
                value,
                name === 'all' ? '全部' : name,
              ]}
            />
            <Line
              type="monotone"
              dataKey={CHART_LINE_CONFIG[filter].dataKey}
              stroke={CHART_LINE_CONFIG[filter].stroke}
              dot={false}
              strokeWidth={2}
              name={CHART_LINE_CONFIG[filter].name}
            />
            {filter === 'all' && (
              <Legend
                formatter={(value) => (value === 'all' ? '全部' : value)}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Recent scans table */}
      <div className="rounded-lg border bg-card overflow-hidden">
        <div className="px-4 py-3 border-b">
          <span className="text-sm font-medium">最近掃描紀錄（最多 50 筆）</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40">
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">時間</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">狀態碼</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">用戶代理</th>
              </tr>
            </thead>
            <tbody>
              {analytics.recent_scans.map((scan, idx) => (
                <tr key={idx} className="border-b last:border-0 hover:bg-muted/20">
                  <td className="px-4 py-2 whitespace-nowrap">
                    <span title={dtf.format(new Date(scan.scanned_at))}>
                      {relativeTime(scan.scanned_at)}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={cn(
                        'inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium',
                        statusBadgeClass(scan.status_code),
                      )}
                    >
                      {scan.status_code}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {formatUa(scan.user_agent)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function absoluteTime(isoDate: string | null): string {
  if (!isoDate) return '永不過期'
  return dtf.format(new Date(isoDate))
}

function validateUrl(value: string): string | undefined {
  if (!value.trim()) return '請輸入網址'
  const result = urlSchema.safeParse(value.trim())
  return result.success ? undefined : result.error.issues[0].message
}

function EditUrlForm({
  initialUrl,
  token,
  onCancel,
  onSuccess,
}: {
  initialUrl: string
  token: string
  onCancel: () => void
  onSuccess: () => void
}) {
  const queryClient = useQueryClient()

  const mutation = useMutation<GetLinkResponse, ApiError, string>({
    mutationFn: (url: string) => patchLink(token, { original_url: url }),
    onSuccess(data) {
      queryClient.setQueryData(linkKey(token), data)
      queryClient.invalidateQueries({ queryKey: ['link'] })
      toast.success('網址已更新', getToastOptions('success'))
      onSuccess()
    },
    onError(err) {
      if (err.status !== 422) {
        toast.error('更新失敗，請稍後再試。', getToastOptions('error'))
      }
    },
  })

  const form = useForm({
    defaultValues: { url: initialUrl },
    onSubmit({ value }) {
      mutation.mutate(value.url.trim())
    },
  })

  const apiError = mutation.error

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        e.stopPropagation()
        form.handleSubmit()
      }}
      className="flex flex-col gap-2"
    >
      <form.Field
        name="url"
        validators={{
          onChange: ({ value }) => validateUrl(value),
          onBlur: ({ value }) => validateUrl(value),
          onSubmit: ({ value }) => validateUrl(value),
        }}
      >
        {(field) => {
          const inlineError =
            field.state.meta.isTouched && field.state.meta.errors.length > 0
              ? String(field.state.meta.errors[0])
              : mutation.isError && apiError?.status === 422
                ? apiError.detail
                : null

          return (
            <div className="flex flex-col gap-1">
              <input
                type="text"
                className={[
                  'rounded-md border px-3 py-2 text-sm outline-none',
                  'focus:ring-2 focus:ring-primary/50',
                  inlineError
                    ? 'border-destructive focus:ring-destructive/50'
                    : 'border-input',
                ].join(' ')}
                value={field.state.value}
                onChange={(e) => field.handleChange(e.target.value)}
                onBlur={field.handleBlur}
                disabled={mutation.isPending}
                autoFocus
              />
              {inlineError && (
                <span className="text-xs text-destructive">{inlineError}</span>
              )}
            </div>
          )
        }}
      </form.Field>

      <div className="flex gap-2">
        <Button
          type="submit"
          size="sm"
          disabled={mutation.isPending}
          className={mutation.isPending ? 'grayscale' : ''}
        >
          {mutation.isPending ? (
            <>
              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              儲存中…
            </>
          ) : (
            '儲存'
          )}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onCancel}
          disabled={mutation.isPending}
        >
          取消
        </Button>
      </div>
    </form>
  )
}

export function LinkDetail() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const qrContainerRef = useRef<HTMLDivElement>(null)
  const rendererRef = useRef<QRRenderer | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [isDeleted, setIsDeleted] = useState(false)

  const query = useQuery<GetLinkResponse, ApiError>({
    queryKey: linkKey(token!),
    queryFn: () => getLink(token!),
    retry: (_count, error) => error.status !== 404,
    enabled: !!token,
  })

  const status: DerivedStatus = isDeleted
    ? 'deleted'
    : query.isError && query.error.status === 404
      ? 'missing'
      : (query.data?.status ?? 'active')

  const shortUrl = token ? `${BASE_URL}/r/${token}` : null

  useEffect(() => {
    if (!query.data || !qrContainerRef.current) return

    rendererRef.current?.destroy()
    const style = getStyle(token!)
    const renderer = createRenderer({
      data: shortUrl!,
      width: Math.min(style.size, 280),
      height: Math.min(style.size, 280),
      dotsOptions: {
        color: style.foreground,
        type: style.dotType as import('qr-code-styling').DotType,
      },
      backgroundOptions: { color: style.background },
    })
    renderer.attachTo(qrContainerRef.current)
    rendererRef.current = renderer
  }, [query.data, shortUrl, token])

  useEffect(() => {
    return () => {
      rendererRef.current?.destroy()
    }
  }, [])

  const deleteMutation = useMutation<void, ApiError>({
    mutationFn: () => deleteLink(token!),
    onSuccess() {
      markDeleted(token!)
      setIsDeleted(true)
      setShowDeleteConfirm(false)
      queryClient.invalidateQueries({ queryKey: ['link'] })
      toast.success('連結已刪除', getToastOptions('success'))
    },
    onError() {
      toast.error('刪除失敗，請稍後再試。', getToastOptions('error'))
    },
  })

  if (!token) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-muted-foreground">無效的連結。</p>
        <button
          type="button"
          onClick={() => navigate('/dashboard')}
          className="self-start text-sm text-primary underline"
        >
          回到儀表板
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <button
        type="button"
        onClick={() => navigate('/dashboard')}
        className="self-start inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        儀表板
      </button>

      <div className="flex items-center gap-2 flex-wrap">
        <h1 className="text-2xl font-bold font-mono">{token}</h1>
        {query.isLoading ? (
          <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground animate-pulse">
            載入中
          </span>
        ) : (
          <StatusBadge status={status} />
        )}
      </div>

      {query.isLoading && (
        <div className="flex items-center gap-2 text-muted-foreground text-sm">
          <Loader2 className="h-4 w-4 animate-spin" />
          載入連結資訊…
        </div>
      )}

      {query.isError && status === 'missing' && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          找不到此連結。它可能已從系統中移除。
        </div>
      )}

      {query.isError && status !== 'missing' && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          載入連結資訊時發生錯誤，請稍後再試。
        </div>
      )}

      {query.data && (
        <>
          <div className="rounded-lg border bg-card p-5 flex flex-col gap-4">
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
              連結資訊
            </h2>

            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">目標網址</span>
                {!isEditing && status !== 'deleted' && (
                  <button
                    type="button"
                    onClick={() => setIsEditing(true)}
                    className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <Pencil className="h-3 w-3" />
                    編輯
                  </button>
                )}
              </div>
              {isEditing ? (
                <EditUrlForm
                  initialUrl={query.data.original_url}
                  token={token}
                  onCancel={() => setIsEditing(false)}
                  onSuccess={() => setIsEditing(false)}
                />
              ) : (
                <p className="text-sm font-mono break-all">{query.data.original_url}</p>
              )}
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-sm font-medium">短網址</span>
              <div className="flex items-center text-sm font-mono text-muted-foreground">
                <span className="break-all">{shortUrl}</span>
                {shortUrl && <CopyButton text={shortUrl} />}
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
              <div>
                <span className="block text-xs text-muted-foreground">建立時間</span>
                <span className="font-medium">{absoluteTime(query.data.created_at)}</span>
              </div>
              <div>
                <span className="block text-xs text-muted-foreground">更新時間</span>
                <span className="font-medium">{absoluteTime(query.data.updated_at)}</span>
              </div>
              <div>
                <span className="block text-xs text-muted-foreground">到期時間</span>
                <span className="font-medium">{absoluteTime(query.data.expires_at)}</span>
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
              QR 碼
            </h2>
            <div className="inline-flex rounded-lg border bg-white p-4 self-start">
              <div ref={qrContainerRef} />
            </div>
            <p className="text-xs text-muted-foreground">
              QR 碼編碼的是短網址，修改目標網址不會更改 QR 碼像素。
            </p>
          </div>

          {status !== 'deleted' && (
            <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-5 flex flex-col gap-3">
              <h2 className="text-sm font-semibold text-destructive uppercase tracking-wide">
                危險操作
              </h2>
              <p className="text-sm text-muted-foreground">
                刪除後此連結將無法再被重新導向（回傳 410），且此操作無法復原。
              </p>
              {!showDeleteConfirm ? (
                <Button
                  variant="destructive"
                  size="sm"
                  className="self-start"
                  onClick={() => setShowDeleteConfirm(true)}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  刪除此連結
                </Button>
              ) : (
                <div className="flex flex-col gap-3 rounded-md border border-destructive/30 bg-destructive/10 p-4">
                  <p className="text-sm font-medium text-destructive">
                    確定要刪除嗎？此操作無法復原。
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => deleteMutation.mutate()}
                      disabled={deleteMutation.isPending}
                      className={deleteMutation.isPending ? 'grayscale' : ''}
                    >
                      {deleteMutation.isPending ? (
                        <>
                          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                          刪除中…
                        </>
                      ) : (
                        '確認刪除'
                      )}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setShowDeleteConfirm(false)}
                      disabled={deleteMutation.isPending}
                    >
                      取消
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}

          {isDeleted && (
            <div className="rounded-lg border border-border bg-muted/30 p-4 flex flex-col gap-2">
              <p className="text-sm text-muted-foreground">
                此連結已刪除，短網址目前回傳 410。
              </p>
              <button
                type="button"
                onClick={() => navigate('/dashboard')}
                className="self-start text-sm text-primary underline underline-offset-2 hover:opacity-80"
              >
                回到儀表板
              </button>
            </div>
          )}

          <div className="flex flex-col gap-3">
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
              分析資料
            </h2>
            <AnalyticsSection token={token} />
          </div>
        </>
      )}
    </div>
  )
}
