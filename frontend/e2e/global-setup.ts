import { execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { FullConfig } from '@playwright/test'

interface MintedCookie {
  name: string
  value: string
  uid: number
}

// Mint a real session cookie by running the Python helper against the dev DB,
// then persist it as Playwright storageState so every test starts authenticated
// without touching Google (bead 8vd). The helper shares the backend's SECRET +
// DATABASE_URL via env — SECRET MUST match the value the running backend uses,
// or the signature won't verify.
async function globalSetup(_config: FullConfig): Promise<void> {
  const here = dirname(fileURLToPath(import.meta.url))
  const repoRoot = resolve(here, '..', '..')
  const env = {
    ...process.env,
    // The helper imports `backend.*`; make the repo root importable regardless
    // of how Python resolves sys.path for a bare script invocation.
    PYTHONPATH: repoRoot,
    SECRET: process.env.SECRET ?? 'e2e-test-secret',
    DATABASE_URL:
      process.env.DATABASE_URL ??
      'postgresql://postgres:postgres@localhost:5432/qr_codes',
  }

  let cookie: MintedCookie
  try {
    const raw = execFileSync('python', ['scripts/mint_session_cookie.py'], {
      cwd: repoRoot,
      env,
      encoding: 'utf-8',
    })
    cookie = JSON.parse(raw) as MintedCookie
  } catch (error) {
    throw new Error(
      `Failed to mint session cookie (is Postgres up and SECRET set to match the backend?): ${String(error)}`,
    )
  }

  const storageState = {
    cookies: [
      {
        name: cookie.name,
        value: cookie.value,
        domain: 'localhost',
        path: '/',
        expires: -1,
        httpOnly: true,
        secure: false,
        sameSite: 'Lax' as const,
      },
    ],
    origins: [],
  }

  const statePath = resolve(here, '.auth', 'state.json')
  mkdirSync(dirname(statePath), { recursive: true })
  writeFileSync(statePath, JSON.stringify(storageState, null, 2))
}

export default globalSetup
