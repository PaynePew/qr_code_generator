import { describe, it, expect } from 'vitest'
import { getToastOptions } from './toastOptions'

describe('getToastOptions', () => {
  it('success → 4 000 ms', () => {
    expect(getToastOptions('success').duration).toBe(4000)
  })

  it('warning → 6 000 ms', () => {
    expect(getToastOptions('warning').duration).toBe(6000)
  })

  it('error → Infinity (sticky)', () => {
    expect(getToastOptions('error').duration).toBe(Infinity)
  })
})
