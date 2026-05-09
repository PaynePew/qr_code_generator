import { useCallback, useEffect, useRef, useState } from 'react'
import { useForm } from '@tanstack/react-form'
import { useMutation } from '@tanstack/react-query'
import { useDropzone, type FileRejection } from 'react-dropzone'
import { Loader2, CheckCircle2, Upload, X, ChevronDown, ChevronRight } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import confetti from 'canvas-confetti'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { ColorPickerField } from '@/components/ui/ColorPickerField'
import { urlSchema, URL_MAX_LENGTH } from '@/schemas/url'
import { createQr } from '@/api/qr'
import { create as createRenderer, type QRRenderer, type RendererOptions } from '@/qr/renderer'
import type { ApiError } from '@/api/client'
import { addToken } from '@/state/linkHistory'
import {
  getDefault,
  setDefault,
  getStyle,
  setStyle as persistSetStyle,
  DEFAULT_STYLE,
  type QRStyle,
  type DotType,
  type ECL,
} from '@/state/styleStore'
import { applyEclPolicy } from '@/qr/eclPolicy'
import { useMotionPreference } from '@/lib/motionPreference'
import { getToastOptions } from '@/lib/toastOptions'
import {
  computeExpiresAt,
  toDatetimeLocalValue,
  type ExpiresAtPreset,
} from '@/lib/expiresAtPresets'

const BASE_URL = import.meta.env.VITE_BASE_URL ?? window.location.origin

const LOGO_MAX_BYTES = 2 * 1024 * 1024

const DOT_TYPES: { value: DotType; label: string }[] = [
  { value: 'square', label: '方形' },
  { value: 'dots', label: '圓點' },
  { value: 'rounded', label: '圓角' },
  { value: 'extra-rounded', label: '超圓角' },
  { value: 'classy', label: '精緻' },
]

const ECL_OPTIONS: { value: ECL; label: string }[] = [
  { value: 'L', label: 'L（低）' },
  { value: 'M', label: 'M（中）' },
  { value: 'Q', label: 'Q（較高）' },
  { value: 'H', label: 'H（高）' },
]

function validateUrl(value: string): string | undefined {
  if (!value) return '請輸入網址'
  const result = urlSchema.safeParse(value)
  return result.success ? undefined : result.error.issues[0].message
}

function styleToRendererOptions(
  style: QRStyle,
  data?: string,
  logoUrl?: string | null,
  logoScale?: number,
): RendererOptions {
  const dotType = style.dotType as import('qr-code-styling').DotType

  let cornerSquareType: 'square' | 'dot' | 'extra-rounded' = 'square'
  let cornerDotType: 'square' | 'dot' = 'square'
  if (style.dotType === 'dots') {
    cornerSquareType = 'dot'
    cornerDotType = 'dot'
  } else if (style.dotType === 'rounded' || style.dotType === 'extra-rounded') {
    cornerSquareType = 'extra-rounded'
    cornerDotType = 'dot'
  }

  const { ecl } = applyEclPolicy(!!logoUrl, style.ecl)

  return {
    ...(data ? { data } : {}),
    width: style.size,
    height: style.size,
    dotsOptions: { color: style.foreground, type: dotType },
    backgroundOptions: { color: style.background },
    cornersSquareOptions: { type: cornerSquareType },
    cornersDotOptions: { type: cornerDotType },
    qrOptions: { errorCorrectionLevel: ecl },
    ...(logoUrl
      ? {
          image: logoUrl,
          imageOptions: {
            imageSize: logoScale ?? 0.2,
            margin: 4,
            hideBackgroundDots: true,
          },
        }
      : { image: '' }),
  }
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
  const [logoScale, setLogoScale] = useState(0.2)
  const [logoError, setLogoError] = useState<string | null>(null)

  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [expiresPreset, setExpiresPreset] = useState<ExpiresAtPreset>('never')
  const [customExpiresAt, setCustomExpiresAt] = useState<string>(() =>
    toDatetimeLocalValue(new Date(Date.now() + 30 * 24 * 60 * 60 * 1000)),
  )

  function getExpiresAtForApi(): string | null {
    if (expiresPreset === 'never') return null
    if (expiresPreset === 'custom') {
      return customExpiresAt ? new Date(customExpiresAt).toISOString() : null
    }
    return computeExpiresAt(new Date(), expiresPreset)
  }

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
      rendererRef.current?.destroy()
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
    updateRenderer(newStyle, logoObjectUrl, logoScale)
  }

  function updateRenderer(s: QRStyle, logoUrl: string | null, scale: number) {
    rendererRef.current?.update(styleToRendererOptions(s, undefined, logoUrl, scale))
  }

  function handleLogoRemove() {
    revokeLogo()
    setLogoObjectUrl(null)
    setLogoError(null)
    updateRenderer(style, null, logoScale)
  }

  function handleLogoScaleChange(scale: number) {
    setLogoScale(scale)
    updateRenderer(style, logoObjectUrl, scale)
  }

  const onDrop = useCallback(
    (acceptedFiles: File[], rejectedFiles: FileRejection[]) => {
      setLogoError(null)

      if (rejectedFiles.length > 0) {
        const err = rejectedFiles[0].errors[0]
        if (err.code === 'file-too-large') {
          setLogoError('檔案超過 2 MB 上限，請選擇較小的圖片。')
        } else if (err.code === 'file-invalid-type') {
          setLogoError('不支援的檔案類型，請上傳 PNG、JPG 或 WebP 圖片。')
        } else {
          setLogoError('無法上傳此檔案，請重試。')
        }
        return
      }

      if (acceptedFiles.length === 0) return

      const file = acceptedFiles[0]
      revokeLogo()

      const objectUrl = URL.createObjectURL(file)
      logoObjectUrlRef.current = objectUrl
      setLogoObjectUrl(objectUrl)
      updateRenderer(style, objectUrl, logoScale)
    },
    [style, logoScale],
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'image/png': [], 'image/jpeg': [], 'image/webp': [] },
    maxSize: LOGO_MAX_BYTES,
    multiple: false,
  })

  const mutation = useMutation({
    mutationFn: createQr,
    onSuccess(data) {
      addToken({
        token: data.token,
        originalUrl: data.original_url,
        createdAt: new Date().toISOString(),
      })
      const qrUrl = `${BASE_URL}/r/${data.token}`
      setShortUrl(qrUrl)
      setCurrentToken(data.token)
      setJitterKey((k) => k + 1)

      persistSetStyle(data.token, style)

      rendererRef.current?.destroy()
      rendererRef.current = null

      const renderer = createRenderer(styleToRendererOptions(style, qrUrl, logoObjectUrl, logoScale))
      rendererRef.current = renderer

      if (qrContainerRef.current) {
        renderer.attachTo(qrContainerRef.current)
      }

      toast.success('QR 碼已產生！', getToastOptions('success'))

      if (!prefersReducedMotion) {
        confetti({ particleCount: 100, spread: 70, origin: { y: 0.6 } })
      }
    },
    onError(err) {
      const apiErr = err as unknown as ApiError
      if (apiErr.isNetwork || apiErr.status !== 422) {
        toast.error('網路錯誤，請稍後再試。', getToastOptions('error'))
      }
    },
  })

  useEffect(() => {
    if (currentToken) {
      const saved = getStyle(currentToken)
      setStyle(saved)
    }
  }, [currentToken])

  const form = useForm({
    defaultValues: { url: '' },
    onSubmit({ value }) {
      mutation.mutate({ url: value.url, expires_at: getExpiresAtForApi() })
    },
  })

  async function handleDownload() {
    if (!rendererRef.current || !currentToken) return
    const blob = await rendererRef.current.toBlob('png')
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `qr-${currentToken}.png`
    a.click()
    URL.revokeObjectURL(url)
  }

  const apiError = mutation.error as ApiError | null

  function handleReset() {
    setShortUrl(null)
    setCurrentToken(null)
    rendererRef.current?.destroy()
    rendererRef.current = null
    const defaultStyle = getDefault()
    setStyle(defaultStyle)
    setExpiresPreset('never')
    setCustomExpiresAt(toDatetimeLocalValue(new Date(Date.now() + 30 * 24 * 60 * 60 * 1000)))
    form.reset()
    mutation.reset()
  }

  const { ecl: effectiveEcl, isLocked: eclLocked } = applyEclPolicy(!!logoObjectUrl, style.ecl)

  return (
    <div className="flex flex-col gap-6 max-w-lg">
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
                    'rounded-md border px-3 py-2 text-sm outline-none',
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

        {/* Advanced settings (expiry) */}
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

              {/* Preset chips */}
              <div className="flex flex-wrap gap-2">
                {(['+7d', '+30d', '+90d', 'never'] as const).map((preset) => {
                  const labels: Record<string, string> = {
                    '+7d': '+7 天',
                    '+30d': '+30 天',
                    '+90d': '+90 天',
                    never: '永不過期',
                  }
                  const active = expiresPreset === preset
                  return (
                    <button
                      key={preset}
                      type="button"
                      onClick={() => handlePresetClick(preset)}
                      disabled={mutation.isPending}
                      className={[
                        'rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:opacity-50',
                        active
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-input bg-background hover:border-primary/60',
                      ].join(' ')}
                    >
                      {labels[preset]}
                    </button>
                  )
                })}
                <button
                  type="button"
                  onClick={() => setExpiresPreset('custom')}
                  disabled={mutation.isPending}
                  className={[
                    'rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:opacity-50',
                    expiresPreset === 'custom'
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-input bg-background hover:border-primary/60',
                  ].join(' ')}
                >
                  自訂時間
                </button>
              </div>

              {/* Custom datetime picker */}
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
                    className="rounded-md border border-input px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/50 bg-background disabled:opacity-50"
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

      <div
        className={[
          'flex items-center justify-center rounded-lg border bg-white',
          'min-h-[280px] transition-all',
          shortUrl ? 'border-border' : 'border-dashed border-muted-foreground/30',
        ].join(' ')}
      >
        {shortUrl ? (
          <motion.div
            key={jitterKey}
            animate={
              prefersReducedMotion
                ? { opacity: 1 }
                : { x: [-3, 3, -3, 3, 0], opacity: 1 }
            }
            initial={{ opacity: prefersReducedMotion ? 0.5 : 1 }}
            transition={{ duration: 0.35 }}
          >
            <div ref={qrContainerRef} />
          </motion.div>
        ) : (
          <p className="text-sm text-muted-foreground">QR 碼預覽將顯示在這裡</p>
        )}
      </div>

      {/* Customization panel */}
      <div className="rounded-lg border border-border p-4 flex flex-col gap-5">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          外觀設定
        </h2>

        <ColorPickerField
          label="前景色"
          value={style.foreground}
          onChange={(color) => handleStyleChange({ ...style, foreground: color })}
          disabled={mutation.isPending}
        />

        <ColorPickerField
          label="背景色"
          value={style.background}
          onChange={(color) => handleStyleChange({ ...style, background: color })}
          disabled={mutation.isPending}
        />

        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium">尺寸</label>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={200}
              max={800}
              step={10}
              value={style.size}
              onChange={(e) =>
                handleStyleChange({ ...style, size: parseInt(e.target.value, 10) })
              }
              disabled={mutation.isPending}
              className="flex-1 accent-primary disabled:opacity-50"
              aria-label="QR 碼尺寸滑桿"
            />
            <input
              type="number"
              min={200}
              max={800}
              step={10}
              value={style.size}
              onChange={(e) => {
                const v = parseInt(e.target.value, 10)
                if (!isNaN(v) && v >= 200 && v <= 800) {
                  handleStyleChange({ ...style, size: v })
                }
              }}
              disabled={mutation.isPending}
              className="w-20 rounded-md border border-input px-2 py-1 text-sm outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-50"
              aria-label="QR 碼尺寸數值"
            />
            <span className="text-sm text-muted-foreground">px</span>
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="dot-style-select" className="text-sm font-medium">
            點點樣式
          </label>
          <select
            id="dot-style-select"
            value={style.dotType}
            onChange={(e) =>
              handleStyleChange({ ...style, dotType: e.target.value as DotType })
            }
            disabled={mutation.isPending}
            className="rounded-md border border-input px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/50 bg-background disabled:opacity-50"
          >
            {DOT_TYPES.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        {/* ECL select */}
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <label htmlFor="ecl-select" className="text-sm font-medium">
              錯誤修正等級
            </label>
            {eclLocked && (
              <span
                className="text-xs text-amber-600 cursor-help"
                title="插入 Logo 時為確保掃描穩定性，錯誤修正等級必須為 H。"
              >
                （已鎖定）
              </span>
            )}
          </div>
          <select
            id="ecl-select"
            value={effectiveEcl}
            onChange={(e) => handleStyleChange({ ...style, ecl: e.target.value as ECL })}
            disabled={mutation.isPending || eclLocked}
            className="rounded-md border border-input px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/50 bg-background disabled:opacity-50"
            title={eclLocked ? '插入 Logo 時為確保掃描穩定性，錯誤修正等級必須為 H。' : undefined}
          >
            {ECL_OPTIONS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        {/* Logo upload */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium">Logo</label>
            <span
              className="text-xs text-muted-foreground cursor-help"
              title="Logo 僅暫存於記憶體中，重新整理頁面後需重新上傳。"
            >
              （重整後消失）
            </span>
          </div>

          {logoObjectUrl ? (
            <div className="flex items-center gap-3">
              <img
                src={logoObjectUrl}
                alt="Logo 預覽"
                className="h-16 w-16 rounded border border-border object-contain bg-white"
              />
              <div className="flex flex-col gap-2 flex-1">
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-muted-foreground">
                    Logo 大小（{Math.round(logoScale * 100)}%）
                  </label>
                  <input
                    type="range"
                    min={0.1}
                    max={0.25}
                    step={0.01}
                    value={logoScale}
                    onChange={(e) => handleLogoScaleChange(parseFloat(e.target.value))}
                    disabled={mutation.isPending}
                    className="flex-1 accent-primary disabled:opacity-50"
                    aria-label="Logo 大小滑桿"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleLogoRemove}
                  disabled={mutation.isPending}
                  className="flex items-center gap-1 self-start text-xs text-destructive underline underline-offset-2 hover:opacity-80 disabled:opacity-50"
                >
                  <X className="h-3 w-3" />
                  移除 Logo
                </button>
              </div>
            </div>
          ) : (
            <div
              {...getRootProps()}
              className={[
                'flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed px-4 py-6 text-center cursor-pointer transition-colors',
                isDragActive
                  ? 'border-primary bg-primary/5'
                  : 'border-muted-foreground/30 hover:border-primary/50',
                mutation.isPending ? 'opacity-50 pointer-events-none' : '',
              ].join(' ')}
            >
              <input {...getInputProps()} />
              <Upload className="h-6 w-6 text-muted-foreground" />
              <div className="flex flex-col gap-0.5">
                <span className="text-sm text-muted-foreground">
                  {isDragActive ? '放開以上傳' : '拖曳或點擊上傳 Logo'}
                </span>
                <span className="text-xs text-muted-foreground/70">
                  PNG、JPG、WebP，小於 2 MB
                </span>
              </div>
            </div>
          )}

          {logoError && (
            <span className="text-xs text-destructive">{logoError}</span>
          )}
        </div>

        <button
          type="button"
          onClick={() => handleStyleChange({ ...DEFAULT_STYLE })}
          disabled={mutation.isPending}
          className="self-start text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground disabled:opacity-50"
        >
          重設為預設值
        </button>
      </div>

      {shortUrl && (
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleDownload}>
            下載 PNG
          </Button>
          <Button type="button" variant="outline" onClick={handleReset}>
            重新產生
          </Button>
        </div>
      )}
    </div>
  )
}
