/// <reference types="vite/client" />

import type { GoogleIdentityApi } from '@/state/auth/googleIdentity'

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  /** Google OAuth client id used to initialize One Tap (ADR 0009). */
  readonly VITE_GOOGLE_CLIENT_ID?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare global {
  interface Window {
    google?: {
      accounts?: {
        id?: GoogleIdentityApi
      }
    }
  }
}
