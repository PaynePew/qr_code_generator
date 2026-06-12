import { useEffect, useRef, useState } from 'react'
import { HexColorPicker } from 'react-colorful'

type InputMode = 'hex' | 'rgba'

interface Props {
  label: string
  value: string
  onChange: (color: string) => void
  disabled?: boolean
}

function hexToRgba(hex: string): string {
  const m = hex.match(/^#([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i)
  if (!m) return 'rgba(0, 0, 0, 1)'
  return `rgba(${parseInt(m[1], 16)}, ${parseInt(m[2], 16)}, ${parseInt(m[3], 16)}, 1)`
}

function rgbaToHex(rgba: string): string | null {
  const m = rgba.match(/rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})/)
  if (!m) return null
  return '#' + [m[1], m[2], m[3]]
    .map((n) => Math.min(255, parseInt(n, 10)).toString(16).padStart(2, '0'))
    .join('')
}

export function ColorPickerField({ label, value, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<InputMode>('hex')
  const [draftHex, setDraftHex] = useState(value)
  const [draftRgba, setDraftRgba] = useState(() => hexToRgba(value))
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setDraftHex(value)
    setDraftRgba(hexToRgba(value))
  }, [value])

  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  function handlePickerChange(hex: string) {
    setDraftHex(hex)
    setDraftRgba(hexToRgba(hex))
    onChange(hex)
  }

  function handleHexInput(raw: string) {
    setDraftHex(raw)
    if (/^#[0-9a-fA-F]{6}$/.test(raw)) {
      setDraftRgba(hexToRgba(raw))
      onChange(raw)
    }
  }

  function handleRgbaInput(raw: string) {
    setDraftRgba(raw)
    const hex = rgbaToHex(raw)
    if (hex) {
      setDraftHex(hex)
      onChange(hex)
    }
  }

  const inputClass =
    'rounded-md border border-input px-2 py-1 text-sm font-mono outline-hidden focus:ring-2 focus:ring-primary/50 disabled:opacity-50'

  return (
    <div ref={containerRef} className="flex flex-col gap-1 relative">
      <label className="text-sm font-medium">{label}</label>
      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          className="w-8 h-8 rounded border border-input shrink-0 disabled:opacity-50"
          style={{ backgroundColor: value }}
          onClick={() => setOpen((v) => !v)}
          aria-label={`開啟${label}色彩選擇器`}
          disabled={disabled}
        />
        {mode === 'hex' ? (
          <input
            type="text"
            className={`${inputClass} w-28`}
            value={draftHex}
            onChange={(e) => handleHexInput(e.target.value)}
            disabled={disabled}
            placeholder="#000000"
            aria-label={`${label} HEX 輸入`}
          />
        ) : (
          <input
            type="text"
            className={`${inputClass} w-48`}
            value={draftRgba}
            onChange={(e) => handleRgbaInput(e.target.value)}
            disabled={disabled}
            placeholder="rgba(0, 0, 0, 1)"
            aria-label={`${label} RGBA 輸入`}
          />
        )}
        <div className="flex text-xs border border-input rounded-md overflow-hidden">
          <button
            type="button"
            className={`px-2 py-1 transition-colors ${
              mode === 'hex'
                ? 'bg-primary text-primary-foreground'
                : 'bg-background text-muted-foreground hover:bg-muted'
            }`}
            onClick={() => setMode('hex')}
            disabled={disabled}
          >
            HEX
          </button>
          <button
            type="button"
            className={`px-2 py-1 transition-colors ${
              mode === 'rgba'
                ? 'bg-primary text-primary-foreground'
                : 'bg-background text-muted-foreground hover:bg-muted'
            }`}
            onClick={() => setMode('rgba')}
            disabled={disabled}
          >
            RGBA
          </button>
        </div>
      </div>
      {open && !disabled && (
        <div className="absolute top-full left-0 z-10 mt-1 shadow-md rounded-md border border-border bg-background p-2">
          <HexColorPicker color={value} onChange={handlePickerChange} />
        </div>
      )}
    </div>
  )
}
