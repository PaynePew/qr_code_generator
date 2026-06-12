import { useCallback } from 'react'
import { useDropzone, type FileRejection } from 'react-dropzone'
import { Upload, X } from 'lucide-react'
import { ColorPickerField } from '@/components/ui/ColorPickerField'
import { applyEclPolicy } from '@/qr/eclPolicy'
import { DEFAULT_STYLE, type QRStyle, type DotType, type ECL } from '@/state/styleStore'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface QRCustomizerProps {
  style: QRStyle
  onStyleChange: (style: QRStyle) => void
  logoObjectUrl: string | null
  logoScale: number
  /** Called with an accepted File when the user drops/picks a logo. */
  onLogoAccepted: (file: File) => void
  onLogoRemove: () => void
  onLogoScaleChange: (scale: number) => void
  logoError?: string | null
  onLogoError?: (msg: string | null) => void
  disabled?: boolean
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Reusable QR customization panel: colour pickers, dot-style, ECL, logo drop
 * zone / preview / scale, and a reset button.
 *
 * Stateless with respect to the style — the parent owns QRStyle and passes
 * callbacks. Logo object-URL lifecycle (create / revoke) is also the parent's
 * concern; this component only calls the provided handlers.
 *
 * Used in both Generator (new link) and LinkDetail (re-edit existing link).
 */
export function QRCustomizer({
  style,
  onStyleChange,
  logoObjectUrl,
  logoScale,
  onLogoAccepted,
  onLogoRemove,
  onLogoScaleChange,
  logoError,
  onLogoError,
  disabled = false,
}: QRCustomizerProps) {
  const { ecl: effectiveEcl, isLocked: eclLocked } = applyEclPolicy(
    !!logoObjectUrl,
    style.ecl,
  )

  const onDrop = useCallback(
    (acceptedFiles: File[], rejectedFiles: FileRejection[]) => {
      onLogoError?.(null)

      if (rejectedFiles.length > 0) {
        const err = rejectedFiles[0].errors[0]
        if (err.code === 'file-too-large') {
          onLogoError?.('檔案超過 2 MB 上限，請選擇較小的圖片。')
        } else if (err.code === 'file-invalid-type') {
          onLogoError?.('不支援的檔案類型，請上傳 PNG、JPG 或 WebP 圖片。')
        } else {
          onLogoError?.('無法上傳此檔案，請重試。')
        }
        return
      }

      if (acceptedFiles.length === 0) return
      onLogoAccepted(acceptedFiles[0])
    },
    [onLogoAccepted, onLogoError],
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'image/png': [], 'image/jpeg': [], 'image/webp': [] },
    maxSize: LOGO_MAX_BYTES,
    multiple: false,
    disabled,
  })

  return (
    <div className="flex flex-col gap-5">
      <ColorPickerField
        label="前景色"
        value={style.foreground}
        onChange={(color) => onStyleChange({ ...style, foreground: color })}
        disabled={disabled}
      />

      <ColorPickerField
        label="背景色"
        value={style.background}
        onChange={(color) => onStyleChange({ ...style, background: color })}
        disabled={disabled}
      />

      {/* Dot style */}
      <div className="flex flex-col gap-1">
        <label htmlFor="qrc-dot-style-select" className="text-sm font-medium">
          點點樣式
        </label>
        <select
          id="qrc-dot-style-select"
          value={style.dotType}
          onChange={(e) =>
            onStyleChange({ ...style, dotType: e.target.value as DotType })
          }
          disabled={disabled}
          className="rounded-md border border-input px-3 py-2 text-sm outline-hidden focus:ring-2 focus:ring-primary/50 bg-background disabled:opacity-50"
        >
          {DOT_TYPES.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {/* ECL */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <label htmlFor="qrc-ecl-select" className="text-sm font-medium">
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
          id="qrc-ecl-select"
          value={effectiveEcl}
          onChange={(e) =>
            onStyleChange({ ...style, ecl: e.target.value as ECL })
          }
          disabled={disabled || eclLocked}
          className="rounded-md border border-input px-3 py-2 text-sm outline-hidden focus:ring-2 focus:ring-primary/50 bg-background disabled:opacity-50"
          title={
            eclLocked
              ? '插入 Logo 時為確保掃描穩定性，錯誤修正等級必須為 H。'
              : undefined
          }
        >
          {ECL_OPTIONS.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {/* Logo */}
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
                  onChange={(e) => onLogoScaleChange(parseFloat(e.target.value))}
                  disabled={disabled}
                  className="flex-1 accent-primary disabled:opacity-50"
                  aria-label="Logo 大小滑桿"
                />
              </div>
              <button
                type="button"
                onClick={onLogoRemove}
                disabled={disabled}
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
              disabled ? 'opacity-50 pointer-events-none' : '',
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

      {/* Reset */}
      <button
        type="button"
        onClick={() => onStyleChange({ ...DEFAULT_STYLE })}
        disabled={disabled}
        className="self-start text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground disabled:opacity-50"
      >
        重設為預設值
      </button>
    </div>
  )
}
