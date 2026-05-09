import { z } from 'zod'

export const URL_MAX_LENGTH = 2048

export const urlSchema = z
  .string()
  .max(URL_MAX_LENGTH, `網址長度不可超過 ${URL_MAX_LENGTH} 個字元`)
  .refine(
    (val) => {
      try {
        new URL(val)
        return true
      } catch {
        return false
      }
    },
    { message: '請輸入有效的網址格式' },
  )
  .refine(
    (val) => {
      try {
        const { protocol } = new URL(val)
        return protocol === 'http:' || protocol === 'https:'
      } catch {
        return false
      }
    },
    { message: '僅支援 http 或 https 網址' },
  )
