import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from '@tanstack/react-form'
import { toast } from 'sonner'
import { ArrowLeft, Loader2, Trash2, Pencil } from 'lucide-react'
import { getLink, patchLink, deleteLink, type GetLinkResponse } from '@/api/qr'
import { linkKey } from '@/api/queryKeys'
import type { ApiError } from '@/api/client'
import { urlSchema } from '@/schemas/url'
import { getStyle } from '@/state/styleStore'
import { create as createRenderer, type QRRenderer } from '@/qr/renderer'
import { markDeleted } from '@/state/linkHistory'
import { getToastOptions } from '@/lib/toastOptions'
import { computeExpiresAt, toDatetimeLocalValue, type ExpiresAtPreset } from '@/lib/expiresAtPresets'
import { Button } from '@/components/ui/button'
import { CopyButton } from '@/components/ui/CopyButton'
import { StatusBadge, type DerivedStatus } from '@/components/ui/StatusBadge'

const BASE_URL = import.meta.env.VITE_BASE_URL ?? window.location.origin

const dtf = new Intl.DateTimeFormat('zh-TW', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

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

function EditExpiresAtForm({
  initialExpiresAt,
  token,
  onCancel,
  onSuccess,
}: {
  initialExpiresAt: string | null
  token: string
  onCancel: () => void
  onSuccess: () => void
}) {
  const queryClient = useQueryClient()

  const [preset, setPreset] = useState<ExpiresAtPreset>(() =>
    initialExpiresAt === null ? 'never' : 'custom',
  )
  const [customValue, setCustomValue] = useState<string>(() => {
    if (initialExpiresAt) return toDatetimeLocalValue(new Date(initialExpiresAt))
    return toDatetimeLocalValue(new Date(Date.now() + 30 * 24 * 60 * 60 * 1000))
  })

  function getExpiresAt(): string | null {
    if (preset === 'never') return null
    if (preset === 'custom') return customValue ? new Date(customValue).toISOString() : null
    return computeExpiresAt(new Date(), preset)
  }

  function handlePresetClick(p: ExpiresAtPreset) {
    setPreset(p)
    if (p !== 'never' && p !== 'custom') {
      const iso = computeExpiresAt(new Date(), p)!
      setCustomValue(toDatetimeLocalValue(new Date(iso)))
    }
  }

  const mutation = useMutation<GetLinkResponse, ApiError, string | null>({
    mutationFn: (expires_at) => patchLink(token, { expires_at }),
    onSuccess(data) {
      queryClient.setQueryData(linkKey(token), data)
      queryClient.invalidateQueries({ queryKey: ['link'] })
      toast.success('到期時間已更新', getToastOptions('success'))
      onSuccess()
    },
    onError() {
      toast.error('更新失敗，請稍後再試。', getToastOptions('error'))
    },
  })

  const PRESET_LABELS: Record<string, string> = {
    '+7d': '+7 天',
    '+30d': '+30 天',
    '+90d': '+90 天',
    never: '永不過期',
    custom: '自訂時間',
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        {(['+7d', '+30d', '+90d', 'never'] as const).map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => handlePresetClick(p)}
            disabled={mutation.isPending}
            className={[
              'rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:opacity-50',
              preset === p
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-input bg-background hover:border-primary/60',
            ].join(' ')}
          >
            {PRESET_LABELS[p]}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setPreset('custom')}
          disabled={mutation.isPending}
          className={[
            'rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:opacity-50',
            preset === 'custom'
              ? 'border-primary bg-primary text-primary-foreground'
              : 'border-input bg-background hover:border-primary/60',
          ].join(' ')}
        >
          {PRESET_LABELS['custom']}
        </button>
      </div>

      {preset !== 'never' && (
        <input
          type="datetime-local"
          value={customValue}
          onChange={(e) => {
            setCustomValue(e.target.value)
            setPreset('custom')
          }}
          disabled={mutation.isPending}
          className="rounded-md border border-input px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/50 bg-background disabled:opacity-50"
        />
      )}

      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          onClick={() => mutation.mutate(getExpiresAt())}
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
    </div>
  )
}

export function LinkDetail() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const qrContainerRef = useRef<HTMLDivElement>(null)
  const rendererRef = useRef<QRRenderer | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [isEditingExpiry, setIsEditingExpiry] = useState(false)
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
            </div>

            {/* expires_at — always visible, editable */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">到期時間</span>
                {!isEditingExpiry && status !== 'deleted' && (
                  <button
                    type="button"
                    onClick={() => setIsEditingExpiry(true)}
                    className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <Pencil className="h-3 w-3" />
                    編輯
                  </button>
                )}
              </div>
              {isEditingExpiry ? (
                <EditExpiresAtForm
                  initialExpiresAt={query.data.expires_at}
                  token={token}
                  onCancel={() => setIsEditingExpiry(false)}
                  onSuccess={() => setIsEditingExpiry(false)}
                />
              ) : (
                <span className="text-sm font-medium">{absoluteTime(query.data.expires_at)}</span>
              )}
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
        </>
      )}
    </div>
  )
}
