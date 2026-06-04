import { configure } from '@testing-library/react'

// CI runners are slower than dev machines. The default `waitFor` timeout is
// 1000ms, and the useGoogleOneTap hook tests (vi.resetModules + dynamic import
// + async script-load mock chain) were measured at ~1010-1045ms under CI load
// — right on the timeout line, causing intermittent failures. Raise the async
// utility timeout so `waitFor` has headroom; it returns immediately on success,
// so passing assertions are not slowed down.
configure({ asyncUtilTimeout: 5000 })
