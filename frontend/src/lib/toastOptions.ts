export type ToastSeverity = 'success' | 'warning' | 'error'

export function getToastOptions(severity: ToastSeverity): { duration: number } {
  switch (severity) {
    case 'success': return { duration: 4000 }
    case 'warning': return { duration: 6000 }
    case 'error': return { duration: Infinity }
  }
}
