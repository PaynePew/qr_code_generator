import type { LinkStatus } from '@/api/qr'

export type DerivedStatus = LinkStatus | 'missing'

const STATUS_LABEL: Record<DerivedStatus, string> = {
  active: '使用中',
  expired: '已過期',
  deleted: '已刪除',
  missing: '找不到',
}

const STATUS_CLASS: Record<DerivedStatus, string> = {
  active: 'bg-green-100 text-green-800',
  expired: 'bg-amber-100 text-amber-800',
  deleted: 'bg-gray-100 text-gray-500',
  missing: 'bg-red-100 text-red-700',
}

export function StatusBadge({ status, className }: { status: DerivedStatus; className?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${STATUS_CLASS[status]}${className ? ` ${className}` : ''}`}
    >
      {STATUS_LABEL[status]}
    </span>
  )
}
