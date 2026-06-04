import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Same-origin dev proxy (ADR 0009): the SPA and API share an origin in dev so
// the SameSite=Lax session cookie is sent. /api (auth + QR) and /r (public
// redirect) are forwarded to the backend; override the target with API_PROXY_TARGET.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiProxyTarget = env.API_PROXY_TARGET ?? 'http://localhost:8000'

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      proxy: {
        '/api': { target: apiProxyTarget, changeOrigin: true },
        '/r': { target: apiProxyTarget, changeOrigin: true },
      },
    },
    test: {
      environment: 'node',
      environmentMatchGlobs: [
        // Component and hook tests that need a DOM run in jsdom.
        ['src/**/*.component.test.tsx', 'jsdom'],
        ['src/**/*.hook.test.ts', 'jsdom'],
        ['src/**/*.hook.test.tsx', 'jsdom'],
      ],
      globals: true,
      setupFiles: ['./src/test-setup.ts'],
      // waitFor headroom (asyncUtilTimeout=5000 in test-setup) must stay below
      // testTimeout so a stuck waitFor fails with a clean assertion instead of
      // hanging the whole test to the default 5000ms test timeout.
      testTimeout: 20000,
    },
  }
})
