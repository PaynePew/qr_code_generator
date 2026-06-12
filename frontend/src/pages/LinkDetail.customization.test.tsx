/**
 * @vitest-environment jsdom
 *
 * Tests for the QR customization edit flow inside LinkDetail
 * (bead qr_code_generator-yfx): owner can open an inline editor,
 * adjust colours/dot-style/logo and save; demo account gets nudged.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { createElement } from 'react'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------
vi.mock('react-router-dom', () => ({
  useParams: () => ({ token: 'tok1234' }),
  useNavigate: () => vi.fn(),
  Link: ({ children }: { children: React.ReactNode }) => children,
}))

vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn().mockReturnValue({ isLoading: true, isError: false, data: undefined }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: vi.fn().mockReturnValue({ mutateAsync: vi.fn(), isPending: false, error: null }),
}))

vi.mock('@/state/linkEntry', () => ({
  useLinkEntry: vi.fn(),
}))

vi.mock('@/state/useCustomization', () => ({
  useCustomization: vi.fn(),
}))

vi.mock('@/qr/renderer', () => ({
  create: vi.fn(() => ({
    update: vi.fn(),
    attachTo: vi.fn(),
    toBlob: vi.fn().mockResolvedValue(new Blob(['fake-png'], { type: 'image/png' })),
    destroy: vi.fn(),
  })),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/lib/demoNudge', () => ({
  nudgeIfDemoReadOnly: vi.fn(() => false),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({
    children,
    onClick,
    disabled,
    type,
  }: React.ButtonHTMLAttributes<HTMLButtonElement>) =>
    createElement('button', { onClick, disabled, type }, children),
}))

vi.mock('@/components/ui/CopyButton', () => ({
  CopyButton: () => createElement('button', null, 'copy'),
}))

vi.mock('@/components/ui/StatusBadge', () => ({
  StatusBadge: ({ status }: { status: string }) =>
    createElement('span', null, status),
}))

vi.mock('@/components/QRCustomizer', () => ({
  QRCustomizer: ({
    onStyleChange,
    logoObjectUrl,
    disabled,
  }: {
    style: unknown
    onStyleChange: (s: unknown) => void
    logoObjectUrl: string | null
    logoScale: number
    onLogoAccepted: (f: File) => void
    onLogoRemove: () => void
    onLogoScaleChange: (n: number) => void
    disabled?: boolean
  }) =>
    createElement(
      'div',
      {
        'data-testid': 'qr-customizer',
        'data-disabled': disabled ? 'true' : 'false',
        'data-logo': logoObjectUrl ?? '',
      },
      createElement(
        'button',
        {
          'data-testid': 'change-style-btn',
          onClick: () =>
            onStyleChange({
              foreground: '#ff0000',
              background: '#ffffff',
              dotType: 'dots',
              ecl: 'M',
            }),
        },
        'change style',
      ),
    ),
}))

vi.mock('recharts', () => ({
  LineChart: ({ children }: { children: React.ReactNode }) =>
    createElement('div', null, children),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) =>
    createElement('div', null, children),
  Legend: () => null,
}))

vi.mock('date-fns', () => ({
  format: () => '2026-01-01',
  subDays: (d: Date) => d,
  parseISO: (s: string) => new Date(s),
}))

vi.mock('@/api/qr', () => ({
  getAnalytics: vi.fn(),
  getQrImageUrl: vi.fn((token: string, updatedAt?: string) => {
    const base = `/api/qr/${token}/image`
    return updatedAt ? `${base}?v=${encodeURIComponent(updatedAt)}` : base
  }),
  saveCustomization: vi.fn(),
}))

import { useLinkEntry } from '@/state/linkEntry'
import { useCustomization } from '@/state/useCustomization'
import { nudgeIfDemoReadOnly } from '@/lib/demoNudge'
import { toast } from 'sonner'

const useLinkEntryMock = vi.mocked(useLinkEntry)
const useCustomizationMock = vi.mocked(useCustomization)
const nudgeMock = vi.mocked(nudgeIfDemoReadOnly)
const toastMock = vi.mocked(toast)

const MOCK_LINK = {
  token: 'tok1234',
  original_url: 'https://example.com/page',
  short_url: 'https://s.example.com/r/tok1234',
  qr_code_url: '',
  label: null,
  status: 'active' as const,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  expires_at: null,
}

const MOCK_CUSTOMIZATION = {
  token: 'tok1234',
  style: { foreground: '#ff0000', background: '#ffffff', size: 320, dotType: 'square', ecl: 'M' },
  image_url: '/api/qr/tok1234/image',
  logo_url: null,
  updated_at: '2026-06-01T10:00:00Z',
}

function makeLinkEntryStub(overrides = {}) {
  return {
    token: 'tok1234',
    link: MOCK_LINK,
    status: 'active' as const,
    isLoading: false,
    queryError: null,
    updateUrl: Object.assign(vi.fn(), { isPending: false, error: null }),
    updateExpiry: Object.assign(vi.fn(), { isPending: false, error: null }),
    updateLabel: Object.assign(vi.fn(), { isPending: false, error: null }),
    markDeleted: Object.assign(vi.fn(), { isPending: false, error: null }),
    ...overrides,
  }
}

function makeCustomizationStub(overrides = {}) {
  return {
    customization: MOCK_CUSTOMIZATION,
    isLoading: false,
    fetchError: null,
    save: vi.fn().mockResolvedValue({
      token: 'tok1234',
      image_key: 'qr/tok1234/composite.png',
      logo_key: null,
      updated_at: '2026-06-01T11:00:00Z',
    }),
    isSaving: false,
    saveError: null,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  useLinkEntryMock.mockReturnValue(
    makeLinkEntryStub() as ReturnType<typeof useLinkEntry>,
  )
  useCustomizationMock.mockReturnValue(
    makeCustomizationStub() as ReturnType<typeof useCustomization>,
  )
  nudgeMock.mockReturnValue(false)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

import { LinkDetail } from './LinkDetail'

describe('LinkDetail — QR customization edit (bead qr_code_generator-yfx)', () => {
  it('renders an "編輯外觀" button for an active link', () => {
    render(createElement(LinkDetail))
    expect(screen.getByRole('button', { name: /編輯外觀/ })).toBeTruthy()
  })

  it('does NOT show the QRCustomizer panel until "編輯外觀" is clicked', () => {
    render(createElement(LinkDetail))
    expect(screen.queryByTestId('qr-customizer')).toBeNull()
  })

  it('shows the QRCustomizer panel after clicking "編輯外觀"', () => {
    render(createElement(LinkDetail))
    fireEvent.click(screen.getByRole('button', { name: /編輯外觀/ }))
    expect(screen.getByTestId('qr-customizer')).toBeTruthy()
  })

  it('hides the "編輯外觀" button while the edit panel is open', () => {
    render(createElement(LinkDetail))
    fireEvent.click(screen.getByRole('button', { name: /編輯外觀/ }))
    expect(screen.queryByRole('button', { name: /編輯外觀/ })).toBeNull()
  })

  it('shows a "取消" button while the edit panel is open', () => {
    render(createElement(LinkDetail))
    fireEvent.click(screen.getByRole('button', { name: /編輯外觀/ }))
    expect(screen.getByRole('button', { name: /取消/ })).toBeTruthy()
  })

  it('closes the edit panel when "取消" is clicked', () => {
    render(createElement(LinkDetail))
    fireEvent.click(screen.getByRole('button', { name: /編輯外觀/ }))
    fireEvent.click(screen.getByRole('button', { name: /取消/ }))
    expect(screen.queryByTestId('qr-customizer')).toBeNull()
  })

  it('shows a "儲存外觀" button while the edit panel is open', () => {
    render(createElement(LinkDetail))
    fireEvent.click(screen.getByRole('button', { name: /編輯外觀/ }))
    expect(screen.getByRole('button', { name: /儲存外觀/ })).toBeTruthy()
  })

  it('does NOT render "編輯外觀" for a deleted link', () => {
    useLinkEntryMock.mockReturnValue(
      makeLinkEntryStub({ status: 'deleted' }) as ReturnType<typeof useLinkEntry>,
    )
    render(createElement(LinkDetail))
    expect(screen.queryByRole('button', { name: /編輯外觀/ })).toBeNull()
  })

  it('calls customizationHook.save and shows success toast after saving', async () => {
    const save = vi.fn().mockResolvedValue({
      token: 'tok1234',
      image_key: 'qr/tok1234/composite.png',
      logo_key: null,
      updated_at: '2026-06-01T11:00:00Z',
    })
    useCustomizationMock.mockReturnValue(
      makeCustomizationStub({ save }) as ReturnType<typeof useCustomization>,
    )

    render(createElement(LinkDetail))
    fireEvent.click(screen.getByRole('button', { name: /編輯外觀/ }))
    fireEvent.click(screen.getByRole('button', { name: /儲存外觀/ }))

    await waitFor(() => {
      expect(save).toHaveBeenCalled()
    })
  })

  it('shows demo nudge and does not toast success when demo save is rejected', async () => {
    const demoError = { status: 403, code: 'DEMO_READ_ONLY', detail: '', isNetwork: false }
    const save = vi.fn().mockRejectedValue(demoError)
    nudgeMock.mockReturnValue(true)
    useCustomizationMock.mockReturnValue(
      makeCustomizationStub({ save }) as ReturnType<typeof useCustomization>,
    )

    render(createElement(LinkDetail))
    fireEvent.click(screen.getByRole('button', { name: /編輯外觀/ }))
    fireEvent.click(screen.getByRole('button', { name: /儲存外觀/ }))

    await waitFor(() => {
      expect(save).toHaveBeenCalled()
    })
    expect(toastMock.success).not.toHaveBeenCalled()
  })

  it('re-sends the existing logo when only colours are edited (regression: silent logo data-loss, bead qr_code_generator-yfx)', async () => {
    // jsdom lacks object-URL APIs used when re-hydrating the logo into a File.
    URL.createObjectURL = vi.fn(() => 'blob:mock-logo')
    URL.revokeObjectURL = vi.fn()

    // The stored customization HAS a logo, exposed via logo_url.
    const logoBlob = new Blob(['logo-bytes'], { type: 'image/png' })
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(logoBlob),
    })
    vi.stubGlobal('fetch', fetchMock)

    const save = vi.fn().mockResolvedValue({
      token: 'tok1234',
      image_key: 'qr/tok1234/composite.png',
      logo_key: 'qr/tok1234/logo.png',
      updated_at: '2026-06-01T11:00:00Z',
    })
    useCustomizationMock.mockReturnValue(
      makeCustomizationStub({
        customization: { ...MOCK_CUSTOMIZATION, logo_url: '/api/qr/tok1234/logo' },
        save,
      }) as ReturnType<typeof useCustomization>,
    )

    render(createElement(LinkDetail))
    fireEvent.click(screen.getByRole('button', { name: /編輯外觀/ }))

    // The existing logo is fetched from logo_url and seeded into the editor.
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/qr/tok1234/logo'),
    )
    await waitFor(() =>
      expect(screen.getByTestId('qr-customizer').getAttribute('data-logo')).toBe(
        'blob:mock-logo',
      ),
    )

    // Change ONLY the colours/dot-style — leave the logo untouched.
    fireEvent.click(screen.getByTestId('change-style-btn'))
    fireEvent.click(screen.getByRole('button', { name: /儲存外觀/ }))

    // The kept logo must be re-sent so the backend does not clear logo_key.
    await waitFor(() => expect(save).toHaveBeenCalled())
    const savedArgs = save.mock.calls[0][0] as { logo?: unknown }
    expect(savedArgs.logo).toBeInstanceOf(File)
  })
})
