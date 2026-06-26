/**
 * @vitest-environment jsdom
 *
 * Tests for Generator (bead 40o): the size/resolution knob must be absent.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { createElement } from 'react'

// ---------------------------------------------------------------------------
// Module mocks — keep Generator isolated from routing, canvas, and React Query.
// ---------------------------------------------------------------------------
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
  Link: ({ children }: { children: React.ReactNode }) => children,
}))

vi.mock('@/state/linkEntry', () => ({
  useCreateEntry: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    reset: vi.fn(),
  }),
}))

vi.mock('@/qr/renderer', () => ({
  create: () => ({
    update: vi.fn(),
    attachTo: vi.fn(),
    toBlob: vi.fn(),
    destroy: vi.fn(),
  }),
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
  getDownloadFormat: () => 'png',
  setDownloadFormat: vi.fn(),
}))

vi.mock('@/lib/motionPreference', () => ({
  useMotionPreference: () => false,
}))

vi.mock('@/lib/demoNudge', () => ({
  nudgeIfDemoReadOnly: () => false,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('canvas-confetti', () => ({
  default: vi.fn(),
}))

vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) =>
      createElement('div', props, children),
    span: ({ children, ...props }: React.HTMLAttributes<HTMLSpanElement>) =>
      createElement('span', props, children),
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
}))

import { Generator } from './Generator'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Generator — size control absence (bead 40o)', () => {
  it('does NOT render a size/resolution slider in the customization panel', () => {
    render(createElement(Generator))

    // The size range slider must not be present (aria-label used in the original).
    expect(screen.queryByRole('slider', { name: /尺寸/ })).toBeNull()
    expect(screen.queryByLabelText(/QR 碼尺寸滑桿/)).toBeNull()
  })

  it('does NOT render a numeric size input in the customization panel', () => {
    render(createElement(Generator))

    expect(screen.queryByLabelText(/QR 碼尺寸數值/)).toBeNull()
    // No "px" label either
    expect(screen.queryByText(/^px$/)).toBeNull()
  })

  it('still renders the dot style and ECL controls (no regression)', () => {
    render(createElement(Generator))

    expect(screen.getByLabelText(/點點樣式/)).toBeTruthy()
    expect(screen.getByLabelText(/錯誤修正等級/)).toBeTruthy()
  })
})
