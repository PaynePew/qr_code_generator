import QRCodeStyling, { type Options } from 'qr-code-styling'

export type RendererOptions = Partial<Options>

export interface QRRenderer {
  update(options: RendererOptions): void
  attachTo(node: HTMLElement): void
  toBlob(format: 'png' | 'svg' | 'webp'): Promise<Blob>
  destroy(): void
}

export function create(options: RendererOptions): QRRenderer {
  const instance = new QRCodeStyling(options)
  let container: HTMLElement | null = null

  return {
    update(opts: RendererOptions) {
      instance.update(opts)
    },
    attachTo(node: HTMLElement) {
      container = node
      instance.append(node)
    },
    async toBlob(format: 'png' | 'svg' | 'webp'): Promise<Blob> {
      const result = await instance.getRawData(format)
      if (result == null) {
        throw new Error(`getRawData returned null for format: ${format}`)
      }
      return result as Blob
    },
    destroy() {
      if (container) {
        container.innerHTML = ''
        container = null
      }
    },
  }
}
