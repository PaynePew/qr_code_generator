import { describe, it, expect, beforeEach } from 'vitest'
import { getDefault, setDefault, getStyle, setStyle, DEFAULT_STYLE } from './styleStore'

class FakeStorage implements Storage {
  private store = new Map<string, string>()
  get length() { return this.store.size }
  key(index: number) { return Array.from(this.store.keys())[index] ?? null }
  getItem(key: string) { return this.store.get(key) ?? null }
  setItem(key: string, value: string) { this.store.set(key, value) }
  removeItem(key: string) { this.store.delete(key) }
  clear() { this.store.clear() }
}

describe('styleStore', () => {
  let storage: FakeStorage

  beforeEach(() => {
    storage = new FakeStorage()
  })

  it('getDefault returns DEFAULT_STYLE when nothing is stored', () => {
    expect(getDefault(storage)).toEqual(DEFAULT_STYLE)
  })

  it('setDefault / getDefault round-trip', () => {
    const style = { foreground: '#ff0000', background: '#00ff00', size: 400, dotType: 'dots' as const }
    setDefault(style, storage)
    expect(getDefault(storage)).toEqual(style)
  })

  it('getStyle falls back to default when no per-token entry exists', () => {
    const customDefault = { ...DEFAULT_STYLE, foreground: '#ff0000' }
    setDefault(customDefault, storage)
    expect(getStyle('tok1', storage)).toEqual(customDefault)
  })

  it('getStyle falls back to DEFAULT_STYLE when neither token nor default are stored', () => {
    expect(getStyle('tok1', storage)).toEqual(DEFAULT_STYLE)
  })

  it('setStyle / getStyle per-token round-trip', () => {
    const style = { foreground: '#ff0000', background: '#0000ff', size: 500, dotType: 'rounded' as const }
    setStyle('tok1', style, storage)
    expect(getStyle('tok1', storage)).toEqual(style)
  })

  it('namespace separation: qr-style:default and qr-style:{token} are independent', () => {
    const defaultStyle = { ...DEFAULT_STYLE, foreground: '#111111' }
    const tokenStyle = { ...DEFAULT_STYLE, foreground: '#222222' }
    setDefault(defaultStyle, storage)
    setStyle('tok1', tokenStyle, storage)
    expect(getDefault(storage)).toEqual(defaultStyle)
    expect(getStyle('tok1', storage)).toEqual(tokenStyle)
  })

  it('per-token styles are independent from each other', () => {
    const styleA = { ...DEFAULT_STYLE, foreground: '#ff0000' }
    const styleB = { ...DEFAULT_STYLE, foreground: '#0000ff' }
    setStyle('tokA', styleA, storage)
    setStyle('tokB', styleB, storage)
    expect(getStyle('tokA', storage)).toEqual(styleA)
    expect(getStyle('tokB', storage)).toEqual(styleB)
  })

  it('corrupt JSON in default key returns DEFAULT_STYLE', () => {
    storage.setItem('qr-style:default', 'not-valid-json{{')
    expect(getDefault(storage)).toEqual(DEFAULT_STYLE)
  })

  it('corrupt JSON in per-token key falls back to default', () => {
    storage.setItem('qr-style:tok1', '{ broken json }')
    expect(getStyle('tok1', storage)).toEqual(DEFAULT_STYLE)
  })

  it('partial / invalid object in storage returns DEFAULT_STYLE', () => {
    storage.setItem('qr-style:default', JSON.stringify({ foreground: '#ff0000' }))
    expect(getDefault(storage)).toEqual(DEFAULT_STYLE)
  })
})
