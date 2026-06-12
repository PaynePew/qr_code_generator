import { useEffect, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { buttonVariants } from '@/components/ui/button'
import { DOWNLOAD_FORMATS, type DownloadFormat } from '@/state/downloadFormatStore'

const FORMAT_LABELS: Record<DownloadFormat, string> = {
  png: '下載 PNG',
  svg: '下載 SVG',
  webp: '下載 WebP',
}

interface DownloadSplitButtonProps {
  format: DownloadFormat
  onDownload: (format: DownloadFormat) => void
  onFormatChange: (format: DownloadFormat) => void
  disabled?: boolean
}

export function DownloadSplitButton({
  format,
  onDownload,
  onFormatChange,
  disabled = false,
}: DownloadSplitButtonProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  const otherFormats = DOWNLOAD_FORMATS.filter(f => f !== format)

  function handleDropdownSelect(f: DownloadFormat) {
    setOpen(false)
    onFormatChange(f)
    onDownload(f)
  }

  const outline = buttonVariants({ variant: 'outline' })

  return (
    <div ref={containerRef} className="relative flex">
      <button
        type="button"
        disabled={disabled}
        onClick={() => onDownload(format)}
        className={cn(outline, 'rounded-l-md rounded-r-none border-r-0')}
      >
        {FORMAT_LABELS[format]}
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(prev => !prev)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={cn(outline, 'rounded-l-none rounded-r-md px-2')}
      >
        <ChevronDown className="h-4 w-4" />
      </button>
      {open && (
        <div
          role="listbox"
          className="absolute top-full left-0 z-10 mt-1 min-w-28 rounded-md border border-input bg-background shadow-md"
        >
          {otherFormats.map(f => (
            <button
              key={f}
              type="button"
              role="option"
              onClick={() => handleDropdownSelect(f)}
              className="block w-full px-4 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground first:rounded-t-md last:rounded-b-md"
            >
              {FORMAT_LABELS[f]}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
