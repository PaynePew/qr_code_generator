import { describe, it, expect, vi, beforeEach } from 'vitest'
import QRCodeStyling from 'qr-code-styling'
import { create } from '@/qr/renderer'

vi.mock('qr-code-styling', () => ({
  default: vi.fn(),
}))

const MockQRCodeStyling = vi.mocked(QRCodeStyling)

beforeEach(() => {
  MockQRCodeStyling.mockClear()
})

describe('QRRenderer.toBlob', () => {
  it('returns a Blob with image/png type for png format', async () => {
    const pngBlob = new Blob(['fake-png-data'], { type: 'image/png' })
    const getRawData = vi.fn().mockResolvedValue(pngBlob)
    MockQRCodeStyling.mockImplementation(() => ({
      update: vi.fn(),
      append: vi.fn(),
      getRawData,
    }) as never)

    const renderer = create({ width: 128, height: 128, data: 'https://example.com' })
    const result = await renderer.toBlob('png')

    expect(result).toBe(pngBlob)
    expect(result.type).toBe('image/png')
    expect(getRawData).toHaveBeenCalledWith('png')
  })

  it('throws when getRawData returns null', async () => {
    const getRawData = vi.fn().mockResolvedValue(null)
    MockQRCodeStyling.mockImplementation(() => ({
      update: vi.fn(),
      append: vi.fn(),
      getRawData,
    }) as never)

    const renderer = create({ width: 128, height: 128, data: 'https://example.com' })
    await expect(renderer.toBlob('png')).rejects.toThrow()
  })
})
