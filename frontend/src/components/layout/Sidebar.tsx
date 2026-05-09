import { NavLink } from 'react-router-dom'
import { QrCode, LayoutDashboard } from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { to: '/', label: '產生器', icon: QrCode, end: true },
  { to: '/dashboard', label: '儀表板', icon: LayoutDashboard, end: false },
]

interface SidebarProps {
  open: boolean
}

export function Sidebar({ open }: SidebarProps) {
  return (
    <aside
      className={cn(
        'flex flex-col border-r bg-sidebar transition-all duration-200 shrink-0 overflow-hidden',
        open ? 'w-52' : 'w-0 border-r-0',
      )}
      aria-hidden={!open}
    >
      <nav className="flex flex-col gap-1 p-2 pt-3 min-w-[13rem]">
        {navItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                  : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
