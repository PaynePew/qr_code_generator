import { describe, expect, it } from 'vitest'
import { computeExpiresAt } from './expiresAtPresets'

const now = new Date('2024-03-15T10:00:00.000Z')

describe('computeExpiresAt', () => {
  it('returns null for never', () => {
    expect(computeExpiresAt(now, 'never')).toBeNull()
  })

  it('returns null for custom (caller handles picker value)', () => {
    expect(computeExpiresAt(now, 'custom')).toBeNull()
  })

  it('+7d adds exactly 7 days in UTC', () => {
    const result = computeExpiresAt(now, '+7d')
    expect(result).toBe('2024-03-22T10:00:00.000Z')
  })

  it('+30d adds exactly 30 days in UTC', () => {
    const result = computeExpiresAt(now, '+30d')
    expect(result).toBe('2024-04-14T10:00:00.000Z')
  })

  it('+90d adds exactly 90 days in UTC', () => {
    const result = computeExpiresAt(now, '+90d')
    expect(result).toBe('2024-06-13T10:00:00.000Z')
  })

  it('result has explicit Z suffix', () => {
    const result = computeExpiresAt(now, '+7d')
    expect(result).toMatch(/Z$/)
  })

  it('is deterministic with the same now value', () => {
    expect(computeExpiresAt(now, '+30d')).toBe(computeExpiresAt(now, '+30d'))
  })

  it('uses the injected clock, not the real clock', () => {
    const past = new Date('2000-01-01T00:00:00.000Z')
    const result = computeExpiresAt(past, '+7d')
    expect(result).toBe('2000-01-08T00:00:00.000Z')
  })
})
