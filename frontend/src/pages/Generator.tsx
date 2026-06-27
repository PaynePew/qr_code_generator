import { useCallback, useEffect, useRef, useState } from 'react'
import { useForm } from '@tanstack/react-form'
import { Loader2, CheckCircle2, ChevronDown, ChevronRight } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import confetti from 'canvas-confetti'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { DownloadSplitButton } from '@/components/ui/DownloadSplitButton'
import { QRCustomizer } from '@/components/QRCustomizer'
import { urlSchema, URL_MAX_LENGTH } from '@/schemas/url'
import { create as createRenderer, type QRRenderer } from '@/qr/renderer'
import { styleToRendererOptions } from '@/qr/rendererOptions'
import type { ApiError } from '@/api/client'
import { useCreateEntry } from '@/state/linkEntry'
import {
  getDefault,
  setDefault,
  setStyle as persistSetStyle,
  DEFAULT_STYLE,
  QR_RENDER_SIZE,
  type QRStyle,
} from '@/state/styleStore'
import { saveCustomization } from '@/api/qr'
import { useMotionPreference } from '@/lib/motionPreference'
import { getToastOptions } from '@/lib/toastOptions'
import { nudgeIfDemoReadOnly } from '@/lib/demoNudge'
import {
  getDownloadFormat,
  setDownloadFormat,
  type DownloadFormat,
} from '@/state/downloadFormatStore'
import {
  computeExpiresAt,
  resolveExpiresAt,
  toDatetimeLocalValue,
  PRESET_LABELS,
  type ExpiresAtPreset,
} from '@/lib/expiresAtPresets'
import { computePreviewHeight } from '@/lib/mobileLayout'

function validateUrl(value: string): string | undefined {
  if (!value) return '請輸入網址'
  const result = urlSchema.safeParse(value)
  return result.success ? undefined : result.error.issues[0].message
}

export function Generator() {
  const qrContainerRef = useRef<HTMLDivElement>(null)
  const rendererRef = useRef<QRRenderer | null>(null)
  const logoObjectUrlRef = useRef<string | null>(null)

  const [shortUrl, setShortUrl] = useState<string | null>(null)
  const [currentToken, setCurrentToken] = useState<string | null>(null)
  const [style, setStyle] = useState<QRStyle>(() => getDefault())
  const [jitterKey, setJitterKey] = useState(0)
  const prefersReducedMotion = useMotionPreference()

  const [logoObjectUrl, setLogoObjectUrl] = useState<string | null>(null)
  const [logoFile, setLogoFile] = useState<File | null>(null)
  const [logoScale, setLogoScale] = useState(0.2)
  const [logoError, setLogoError] = useState<string | null>(null)

  const [downloadFormat, setDownloadFormatState] = useState<DownloadFormat>(() =>
    getDownloadFormat(),
  )

  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [expiresPreset, setExpiresPreset] = useState<ExpiresAtPreset>('never')
  const [customExpiresAt, setCustomExpiresAt] = useState<string>(() =>
    toDatetimeLocalValue(new Date(computeExpiresAt(new Date(), '+30d')!)),
  )

  // The QR preview encodes the real Short URL once minted, else a placeholder so
  // the owner can preview colours / dots / logo live BEFORE generating.
  const previewData = shortUrl ?? `${window.location.origin}/r/preview`

  // Create the live preview renderer once; it survives the page lifetime.
  useEffect(() => {
    rendererRef.current = createRenderer(
      styleToRendererOptions(style, previewData, logoObjectUrl, logoScale),
    )
    return () => {
      rendererRef.current?.destroy()
      rendererRef.current = null
    }
  }, [])

  // Keep the preview in sync with the style / logo / encoded URL (reactive — no
  // scattered manual update() calls).
  useEffect(() => {
    rendererRef.current?.update(
      styleToRendererOptions(style, previewData, logoObjectUrl, logoScale),
    )
  }, [style, previewData, logoObjectUrl, logoScale])

  // The jitter animation (key=jitterKey) re-mounts the preview container on each
  // generate, detaching the canvas — (re)attach it on mount and after generate.
  useEffect(() => {
    if (rendererRef.current && qrContainerRef.current) {
      rendererRef.current.attachTo(qrContainerRef.current)
    }
  }, [jitterKey])

  // Scroll-based preview shrink (mobile only)
  const [previewScrollY, setPreviewScrollY] = useState(0)
  useEffect(() => {
    const main = document.querySelector('main')
    if (!main) return
    function onScroll() {
      setPreviewScrollY(main!.scrollTop)
    }
    main.addEventListener('scroll', onScroll, { passive: true })
    return () => main.removeEventListener('scroll', onScroll)
  }, [])
  const previewHeight = computePreviewHeight(previewScrollY)

  function handlePresetClick(preset: ExpiresAtPreset) {
    setExpiresPreset(preset)
    if (preset !== 'never' && preset !== 'custom') {
      const iso = computeExpiresAt(new Date(), preset)!
      setCustomExpiresAt(toDatetimeLocalValue(new Date(iso)))
    }
  }


  function revokeLogo() {
    if (logoObjectUrlRef.current) {
      URL.revokeObjectURL(logoObjectUrlRef.current)
      logoObjectUrlRef.current = null
    }
  }

  useEffect(() => {
    return () => {
      // Renderer teardown lives in the create-on-mount effect's cleanup.
      revokeLogo()
    }
  }, [])

  function handleStyleChange(newStyle: QRStyle) {
    setStyle(newStyle)
    if (currentToken) {
      persistSetStyle(currentToken, newStyle)
    } else {
      setDefault(newStyle)
    }
    // The live preview re-renders reactively from `style` (see the sync effect).
  }

  function handleLogoRemove() {
    revokeLogo()
    setLogoObjectUrl(null)
    setLogoFile(null)
    setLogoError(null)
  }

  function handleLogoScaleChange(scale: number) {
    setLogoScale(scale)
  }

  const handleLogoAccepted = useCallback((file: File) => {
    revokeLogo()
    const objectUrl = URL.createObjectURL(file)
    logoObjectUrlRef.current = objectUrl
    setLogoObjectUrl(objectUrl)
    setLogoFile(file)
    setLogoError(null)
  }, [])

  const mutation = useCreateEntry()

  function isCustomized(s: QRStyle, logo: File | null): boolean {
    return (
      s.foreground !== DEFAULT_STYLE.foreground ||
      s.background !== DEFAULT_STYLE.background ||
      s.dotType !== DEFAULT_STYLE.dotType ||
      s.ecl !== DEFAULT_STYLE.ecl ||
      logo !== null
    )
  }

  const onCreateSuccess = async (data: { token: string; original_url: string; short_url: string }) => {
      const qrUrl = data.short_url
      setShortUrl(qrUrl)
      setCurrentToken(data.token)
      setJitterKey((k) => k + 1)

      persistSetStyle(data.token, style)

      // Repoint the live preview renderer at the real Short URL (it already
      // exists from the page's create-on-mount effect).
      rendererRef.current?.update(
        styleToRendererOptions(style, qrUrl, logoObjectUrl, logoScale),
      )

      toast.success('QR 碼已產生！', getToastOptions('success'))

      if (!prefersReducedMotion) {
        confetti({ particleCount: 100, spread: 70, origin: { y: 0.6 } })
      }

      if (isCustomized(style, logoFile)) {
        try {
          const blob = await rendererRef.current?.toBlob('png')
          if (!blob) return
          await saveCustomization({
            token: data.token,
            style: {
              foreground: style.foreground,
              background: style.background,
              dotType: style.dotType,
              ecl: style.ecl,
              size: QR_RENDER_SIZE,
            },
            image: blob,
            logo: logoFile ?? undefined,
          })
        } catch (err) {
          if (nudgeIfDemoReadOnly(err as ApiError)) return
          toast.error('樣式儲存失敗，QR 碼已建立但外觀可能需要重新套用。', getToastOptions('error'))
        }
      }
  }

  const onCreateError = (err: ApiError) => {
    // A guest hitting the read-only demo guard gets a login nudge, not an error.
    if (nudgeIfDemoReadOnly(err)) return
    if (err.isNetwork || err.status !== 422) {
      toast.error('網路錯誤，請稍後再試。', getToastOptions('error'))
    }
  }

  const form = useForm({
    defaultValues: { url: '', label: '' },
    onSubmit({ value }) {
      const trimmedLabel = value.label.trim()
      mutation.mutate(
        {
          url: value.url,
          expires_at: resolveExpiresAt(expiresPreset, customExpiresAt),
          label: trimmedLabel || null,
        },
        { onSuccess: onCreateSuccess, onError: onCreateError },
      )
    },
  })

  async function handleDownload(format: DownloadFormat = downloadFormat) {
    if (!rendererRef.current || !currentToken) return
    const blob = await rendererRef.current.toBlob(format)
    const objectUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = objectUrl
    a.download = `qr-${currentToken}.${format}`
    a.click()
    URL.revokeObjectURL(objectUrl)
  }

  function handleFormatChange(format: DownloadFormat) {
    setDownloadFormatState(format)
    setDownloadFormat(format)
  }

  const apiError = mutation.error as ApiError | null

  function handleReset() {
    setShortUrl(null)
    setCurrentToken(null)
    // The live preview reverts to a default-styled placeholder reactively
    // (shortUrl→null, style→default); the renderer instance is kept.
    const defaultStyle = getDefault()
    setStyle(defaultStyle)
    setExpiresPreset('never')
    setCustomExpiresAt(toDatetimeLocalValue(new Date(computeExpiresAt(new Date(), '+30d')!)))
    form.reset({ url: '', label: '' })
    mutation.reset()
  }

  return (
    <div className="w-full">
      {/* Two-column on lg+: controls left (60%), preview right (40%) */}
      {/* Single-column on mobile: preview on top, controls below */}
      <div className="flex flex-col lg:flex-row lg:gap-8 lg:items-start">

        {/* ── Preview column ── appears first on mobile, second on lg+ */}
        <div className="order-1 lg:order-2 lg:w-2/5 lg:sticky lg:top-6 lg:self-start">
          {/* Mobile: sticky with scroll-based shrink */}
          <div className="sticky top-0 z-10 bg-background pb-2 lg:static lg:z-auto lg:pb-0">
            <div
              className={cn(
                'flex items-center justify-center rounded-lg border bg-white overflow-hidden',
                'transition-all duration-200',
                // Desktop: comfortable breathing room around the centered QR.
                'p-4 lg:p-8',
                shortUrl ? 'border-border' : 'border-dashed border-muted-foreground/30',
              )}
              style={{ minHeight: `${previewHeight}px` }}
            >
              <motion.div
                key={jitterKey}
                animate={
                  !prefersReducedMotion && shortUrl
                    ? { x: [-3, 3, -3, 3, 0], opacity: 1 }
                    : { opacity: 1 }
                }
                initial={{ opacity: prefersReducedMotion ? 0.5 : 1 }}
                transition={{ duration: 0.35 }}
              >
                <div ref={qrContainerRef} />
              </motion.div>
            </div>
            {!shortUrl && (
              <p className="mt-2 text-center text-xs text-muted-foreground">
                即時外觀預覽 — 按「產生 QR 碼」後會編碼正式短網址
              </p>
            )}
          </div>
        </div>

        {/* ── Controls column ── appears second on mobile, first on lg+ */}
        <div className="order-2 lg:order-1 lg:flex-1 flex flex-col gap-6 pt-4 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold">QR 碼產生器</h1>
            <p className="text-muted-foreground mt-1">
              輸入目標網址，即可產生專屬的短網址 QR 碼。
            </p>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              e.stopPropagation()
              form.handleSubmit()
            }}
            className="flex flex-col gap-4"
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

                function handlePaste(e: React.ClipboardEvent<HTMLInputElement>) {
                  const pasted = e.clipboardData.getData('text')
                  const combined = field.state.value + pasted
                  if (combined.length > URL_MAX_LENGTH) {
                    e.preventDefault()
                    const allowed = URL_MAX_LENGTH - field.state.value.length
                    if (allowed > 0) {
                      field.handleChange(field.state.value + pasted.slice(0, allowed))
                    }
                  }
                }

                return (
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-2">
                      <label htmlFor="url-input" className="text-sm font-medium">
                        目標網址
                      </label>
                      <AnimatePresence>
                        {shortUrl && (
                          <motion.span
                            initial={{ opacity: 0, scale: 0.8 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0 }}
                            className="flex items-center gap-1 text-xs text-green-600 font-medium"
                          >
                            <CheckCircle2 className="h-3 w-3" />
                            已產生
                          </motion.span>
                        )}
                      </AnimatePresence>
                    </div>
                    <input
                      id="url-input"
                      type="text"
                      className={[
                        'rounded-md border px-3 py-2 text-sm outline-hidden',
                        'focus:ring-2 focus:ring-primary/50',
                        inlineError
                          ? 'border-destructive focus:ring-destructive/50'
                          : 'border-input',
                      ].join(' ')}
                      placeholder="https://example.com/your-long-url"
                      value={field.state.value}
                      maxLength={URL_MAX_LENGTH}
                      onPaste={handlePaste}
                      onChange={(e) => field.handleChange(e.target.value)}
                      onBlur={field.handleBlur}
                      disabled={mutation.isPending}
                    />
                    <div className="flex justify-between text-xs">
                      <span className={inlineError ? 'text-destructive' : 'text-transparent select-none'}>
                        {inlineError ?? '　'}
                      </span>
                      <span
                        className={
                          field.state.value.length >= URL_MAX_LENGTH
                            ? 'text-destructive'
                            : 'text-muted-foreground'
                        }
                      >
                        {field.state.value.length} / {URL_MAX_LENGTH}
                      </span>
                    </div>
                  </div>
                )
              }}
            </form.Field>

            <form.Field name="label">
              {(field) => (
                <div className="flex flex-col gap-1">
                  <label htmlFor="label-input" className="text-sm font-medium">
                    標籤（選填）
                  </label>
                  <input
                    id="label-input"
                    type="text"
                    maxLength={100}
                    placeholder="例：大廳海報、電子報…"
                    className="rounded-md border border-input px-3 py-2 text-sm outline-hidden focus:ring-2 focus:ring-primary/50"
                    value={field.state.value}
                    onChange={(e) => field.handleChange(e.target.value)}
                    onBlur={field.handleBlur}
                    disabled={mutation.isPending}
                  />
                  <p className="text-xs text-muted-foreground">
                    為此連結取一個好記的名字，方便在儀表板辨識。
                  </p>
                </div>
              )}
            </form.Field>

            <div className="rounded-lg border border-border">
              <button
                type="button"
                onClick={() => setAdvancedOpen((o) => !o)}
                className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium hover:bg-muted/40 transition-colors"
              >
                <span>進階設定</span>
                {advancedOpen ? (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                )}
              </button>

              {advancedOpen && (
                <div className="border-t border-border px-4 py-4 flex flex-col gap-3">
                  <div>
                    <span className="text-sm font-medium">到期設定</span>
                    <p className="text-xs text-muted-foreground mt-0.5">預設為永不過期。</p>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {(['+7d', '+30d', '+90d', 'never', 'custom'] as const).map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        onClick={() => handlePresetClick(preset)}
                        disabled={mutation.isPending}
                        className={[
                          'rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:opacity-50',
                          expiresPreset === preset
                            ? 'border-primary bg-primary text-primary-foreground'
                            : 'border-input bg-background hover:border-primary/60',
                        ].join(' ')}
                      >
                        {PRESET_LABELS[preset]}
                      </button>
                    ))}
                  </div>

                  {expiresPreset !== 'never' && (
                    <div className="flex flex-col gap-1">
                      <label htmlFor="expires-at-input" className="text-xs text-muted-foreground">
                        到期日期與時間（本地時間）
                      </label>
                      <input
                        id="expires-at-input"
                        type="datetime-local"
                        value={customExpiresAt}
                        onChange={(e) => {
                          setCustomExpiresAt(e.target.value)
                          setExpiresPreset('custom')
                        }}
                        disabled={mutation.isPending}
                        className="rounded-md border border-input px-3 py-2 text-sm outline-hidden focus:ring-2 focus:ring-primary/50 bg-background disabled:opacity-50"
                      />
                    </div>
                  )}
                </div>
              )}
            </div>

            <Button
              type="submit"
              disabled={mutation.isPending}
              className={mutation.isPending ? 'grayscale' : ''}
            >
              {mutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  產生中…
                </>
              ) : (
                '產生 QR 碼'
              )}
            </Button>
          </form>

          {/* Customization panel */}
          <div className="rounded-lg border border-border p-4 flex flex-col gap-5">
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
              外觀設定
            </h2>

            <QRCustomizer
              style={style}
              onStyleChange={handleStyleChange}
              logoObjectUrl={logoObjectUrl}
              logoScale={logoScale}
              onLogoAccepted={handleLogoAccepted}
              onLogoRemove={handleLogoRemove}
              onLogoScaleChange={handleLogoScaleChange}
              logoError={logoError}
              onLogoError={setLogoError}
              disabled={mutation.isPending}
            />
          </div>

          {shortUrl && (
            <div className="flex gap-2">
              <DownloadSplitButton
                format={downloadFormat}
                onDownload={handleDownload}
                onFormatChange={handleFormatChange}
              />
              <Button type="button" variant="outline" onClick={handleReset}>
                重新產生
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
