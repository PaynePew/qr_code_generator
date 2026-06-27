/**
 * @vitest-environment jsdom
 *
 * Tests for Generator "save customization on create" (bead 65g):
 * After a successful link creation, if the style is customized OR a logo is
 * present, the composite PNG + style recipe must be uploaded via
 * saveCustomization. For vanilla (DEFAULT_STYLE + no logo) it must NOT upload.
 * If the upload fails, the link is still treated as created and the user gets
 * a friendly error toast.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, waitFor, fireEvent } from '@testing-library/react'
import { createElement } from 'react'

// ---------------------------------------------------------------------------
// Hoisted shared mocks (accessible inside vi.mock factories AND in tests)
// ---------------------------------------------------------------------------
const {
  mutateMock,
  saveCustomizationMock,
  toastSuccessMock,
  toastErrorMock,
  rendererMock,
  fakePngBlob,
} = vi.hoisted(() => {
  const fakePngBlob = new Blob(['fake-png-bytes'], { type: 'image/png' })
  const rendererMock = {
    update: vi.fn(),
    attachTo: vi.fn(),
    toBlob: vi.fn().mockResolvedValue(fakePngBlob),
    destroy: vi.fn(),
  }
  return {
    mutateMock: vi.fn(),
    saveCustomizationMock: vi.fn(),
    toastSuccessMock: vi.fn(),
    toastErrorMock: vi.fn(),
    rendererMock,
    fakePngBlob,
  }
})

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
  Link: ({ children }: { children: React.ReactNode }) => children,
}))

vi.mock('@/state/linkEntry', () => ({
  useCreateEntry: () => ({
    mutate: mutateMock,
    isPending: false,
    isError: false,
    error: null,
    reset: vi.fn(),
  }),
}))

vi.mock('@/qr/renderer', () => ({
  create: vi.fn(() => rendererMock),
}))

vi.mock('@/state/styleStore', () => ({
  getDefault: () => ({
    foreground: '#000000',
    background: '#ffffff',
    dotType: 'square',
    ecl: 'M',
  }),
  setDefault: vi.fn(),
  getStyle: () => ({
    foreground: '#000000',
    background: '#ffffff',
    dotType: 'square',
    ecl: 'M',
  }),
  setStyle: vi.fn(),
  DEFAULT_STYLE: {
    foreground: '#000000',
    background: '#ffffff',
    dotType: 'square',
    ecl: 'M',
  },
  QR_RENDER_SIZE: 320,
}))

vi.mock('@/state/downloadFormatStore', () => ({
  DOWNLOAD_FORMATS: ['png', 'svg', 'webp'],
  getDownloadFormat: () => 'png',
  setDownloadFormat: vi.fn(),
}))

vi.mock('@/lib/motionPreference', () => ({
  useMotionPreference: () => false,
}))

vi.mock('@/lib/demoNudge', () => ({
  nudgeIfDemoReadOnly: () => false,
  nudgeIfUnauthenticated: () => false,
}))

vi.mock('sonner', () => ({
  toast: { success: toastSuccessMock, error: toastErrorMock },
}))

vi.mock('canvas-confetti', () => ({ default: vi.fn() }))

vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) =>
      createElement('div', props, children),
    span: ({ children, ...props }: React.HTMLAttributes<HTMLSpanElement>) =>
      createElement('span', props, children),
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
}))

vi.mock('@/api/qr', () => ({
  saveCustomization: saveCustomizationMock,
  getCustomization: vi.fn(),
}))

import { Generator } from './Generator'

// ---------------------------------------------------------------------------
// jsdom stubs for browser APIs used by Generator / react-dropzone
// ---------------------------------------------------------------------------
beforeEach(() => {
  // react-dropzone needs createObjectURL / revokeObjectURL
  if (!globalThis.URL.createObjectURL) {
    Object.defineProperty(globalThis.URL, 'createObjectURL', {
      value: vi.fn(() => 'blob:fake-url'),
      writable: true,
      configurable: true,
    })
  } else {
    vi.spyOn(globalThis.URL, 'createObjectURL').mockReturnValue('blob:fake-url')
  }
  if (!globalThis.URL.revokeObjectURL) {
    Object.defineProperty(globalThis.URL, 'revokeObjectURL', {
      value: vi.fn(),
      writable: true,
      configurable: true,
    })
  } else {
    vi.spyOn(globalThis.URL, 'revokeObjectURL').mockReturnValue(undefined)
  }
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MOCK_CREATE_RESPONSE = {
  token: 'newtoken1',
  original_url: 'https://example.com/test',
  short_url: 'https://s.example.com/r/newtoken1',
}

/**
 * Render Generator, fill in a URL, click submit, then invoke the captured
 * onSuccess callback directly. Returns after all async work drains.
 */
async function renderSubmitAndFireSuccess(
  response = MOCK_CREATE_RESPONSE,
  setup?: (container: HTMLElement) => void | Promise<void>,
) {
  const { container } = render(createElement(Generator))

  if (setup) {
    await setup(container)
  }

  // Fill in a valid URL so TanStack Form validation passes
  const urlInput = screen.getByPlaceholderText(/https:\/\/example\.com/)
  await act(async () => {
    fireEvent.change(urlInput, { target: { value: 'https://example.com/test-url' } })
  })

  // Click submit — form.handleSubmit() is async; wrap in act so React state settles
  await act(async () => {
    const submitButton = screen.getByRole('button', { name: /產生 QR 碼/ })
    fireEvent.click(submitButton)
  })

  // mutateMock must have been called (form submitted)
  expect(mutateMock).toHaveBeenCalled()
  const lastCall = mutateMock.mock.calls[mutateMock.mock.calls.length - 1]
  const { onSuccess } = lastCall[1] as {
    onSuccess: (data: typeof response) => void | Promise<void>
  }

  await act(async () => {
    await onSuccess(response)
  })

  return { container }
}

beforeEach(() => {
  vi.clearAllMocks()
  rendererMock.toBlob.mockResolvedValue(fakePngBlob)
  saveCustomizationMock.mockResolvedValue({
    token: 'newtoken1',
    image_key: 'qr/newtoken1/composite.png',
    logo_key: null,
    updated_at: '2026-06-05T00:00:00Z',
  })
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Generator — save customization on create (bead 65g)', () => {
  it('does NOT call saveCustomization when style equals DEFAULT_STYLE and no logo', async () => {
    // No changes — component starts with DEFAULT_STYLE, no logo.
    await renderSubmitAndFireSuccess()

    await waitFor(() =>
      expect(toastSuccessMock).toHaveBeenCalledWith('QR 碼已產生！', expect.anything()),
    )
    expect(saveCustomizationMock).not.toHaveBeenCalled()
  })

  it('calls saveCustomization when the dot type is changed (style differs from DEFAULT_STYLE)', async () => {
    await renderSubmitAndFireSuccess(MOCK_CREATE_RESPONSE, () => {
      // Change dot type from 'square' (default) to 'dots'
      const dotSelect = screen.getByLabelText(/點點樣式/)
      fireEvent.change(dotSelect, { target: { value: 'dots' } })
    })

    await waitFor(() => expect(saveCustomizationMock).toHaveBeenCalled())
    const callArgs = saveCustomizationMock.mock.calls[0][0]
    expect(callArgs.token).toBe('newtoken1')
    expect(callArgs.image).toBeInstanceOf(Blob)
    expect(callArgs.style).toMatchObject({
      foreground: '#000000',
      background: '#ffffff',
      dotType: 'dots',
      ecl: 'M',
      size: 320,
    })
    expect(callArgs.logo).toBeFalsy()
  })

  it('calls saveCustomization with the logo File when a logo is present (default style)', async () => {
    const logoFile = new File(['fake-logo-bytes'], 'logo.png', { type: 'image/png' })

    await renderSubmitAndFireSuccess(MOCK_CREATE_RESPONSE, async () => {
      const dropzoneInput = document.querySelector<HTMLInputElement>('input[type="file"]')
      expect(dropzoneInput).toBeTruthy()
      await act(async () => {
        fireEvent.change(dropzoneInput!, { target: { files: [logoFile] } })
      })
      // Wait for logo preview to appear (confirms drop processed)
      await waitFor(() => expect(screen.queryByAltText(/Logo 預覽/)).toBeTruthy())
    })

    await waitFor(() => expect(saveCustomizationMock).toHaveBeenCalled())
    const callArgs = saveCustomizationMock.mock.calls[0][0]
    expect(callArgs.token).toBe('newtoken1')
    expect(callArgs.logo).toBeInstanceOf(File)
  })

  it('shows link-creation success toast even when saveCustomization upload fails', async () => {
    saveCustomizationMock.mockRejectedValueOnce({
      status: 500,
      code: 'SERVER_ERROR',
      detail: 'upload failed',
      isNetwork: false,
    })

    await renderSubmitAndFireSuccess(MOCK_CREATE_RESPONSE, () => {
      // Change dot type to trigger customization path
      const dotSelect = screen.getByLabelText(/點點樣式/)
      fireEvent.change(dotSelect, { target: { value: 'rounded' } })
    })

    // Link creation success toast must still fire
    await waitFor(() =>
      expect(toastSuccessMock).toHaveBeenCalledWith('QR 碼已產生！', expect.anything()),
    )
    // Error toast for customization failure must also appear
    await waitFor(() => expect(toastErrorMock).toHaveBeenCalled())
    const errorMsg = toastErrorMock.mock.calls[0][0] as string
    expect(typeof errorMsg).toBe('string')
    expect(errorMsg.length).toBeGreaterThan(0)
  })

  it('saveCustomization receives a StyleRecipe with size=QR_RENDER_SIZE (320)', async () => {
    await renderSubmitAndFireSuccess(MOCK_CREATE_RESPONSE, () => {
      // Change ECL to trigger customization
      const eclSelect = screen.getByLabelText(/錯誤修正等級/)
      fireEvent.change(eclSelect, { target: { value: 'H' } })
    })

    await waitFor(() => expect(saveCustomizationMock).toHaveBeenCalled())
    const { style } = saveCustomizationMock.mock.calls[0][0]
    expect(style.size).toBe(320)
  })
})
