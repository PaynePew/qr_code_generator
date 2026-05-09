import { useEffect, useRef, useState } from 'react'
import { useForm } from '@tanstack/react-form'
import { useMutation } from '@tanstack/react-query'
import { Loader2, CheckCircle2 } from 'lucide-react'
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
} from '@/state/styleStore'
import { useMotionPreference } from '@/lib/motionPreference'
import { getToastOptions } from '@/lib/toastOptions'

const BASE_URL = import.meta.env.VITE_BASE_URL ?? window.location.origin

const DOT_TYPES: { value: DotType; label: string }[] = [
  { value: 'square', label: '方形' },
  { value: 'dots', label: '圓點' },
  { value: 'rounded', label: '圓角' },
  { value: 'extra-rounded', label: '超圓角' },
  { value: 'classy', label: '精緻' },
]

function validateUrl(value: string): string | undefined {
  if (!value) return '請輸入網址'
  const result = urlSchema.safeParse(value)
  return result.success ? undefined : result.error.issues[0].message
}

function styleToRendererOptions(style: QRStyle, data?: string): RendererOptions {
  const dotType = style.dotType as import('qr-code-styling').DotType

  // Map corner options to complement dot style
  let cornerSquareType: 'square' | 'dot' | 'extra-rounded' = 'square'
  let cornerDotType: 'square' | 'dot' = 'square'
  if (style.dotType === 'dots') {
    cornerSquareType = 'dot'
    cornerDotType = 'dot'
  } else if (style.dotType === 'rounded' || style.dotType === 'extra-rounded') {
    cornerSquareType = 'extra-rounded'
    cornerDotType = 'dot'
  }

  return {
    ...(data ? { data } : {}),
    width: style.size,
    height: style.size,
    dotsOptions: { color: style.foreground, type: dotType },
    backgroundOptions: { color: style.background },
    cornersSquareOptions: { type: cornerSquareType },
    cornersDotOptions: { type: cornerDotType },
  }
}

export function Generator() {
  const qrContainerRef = useRef<HTMLDivElement>(null)
  const rendererRef = useRef<QRRenderer | null>(null)
  const [shortUrl, setShortUrl] = useState<string | null>(null)
  const [currentToken, setCurrentToken] = useState<string | null>(null)
  const [style, setStyle] = useState<QRStyle>(() => getDefault())
  const [jitterKey, setJitterKey] = useState(0)
  const prefersReducedMotion = useMotionPreference()

  useEffect(() => {
    return () => {
      rendererRef.current?.destroy()
    }
  }, [])

  function handleStyleChange(newStyle: QRStyle) {
    setStyle(newStyle)
    if (currentToken) {
      persistSetStyle(currentToken, newStyle)
    } else {
      setDefault(newStyle)
    }
    if (rendererRef.current) {
      rendererRef.current.update(styleToRendererOptions(newStyle))
    }
  }

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

      const renderer = createRenderer(styleToRendererOptions(style, qrUrl))
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
      mutation.mutate({ url: value.url })
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
    form.reset()
    mutation.reset()
  }

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
