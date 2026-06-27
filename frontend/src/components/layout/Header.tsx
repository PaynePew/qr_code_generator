import { Menu } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { LoginControl } from './LoginControl'

// Brand mark — a roast chicken (no icon library ships a whole roasted bird;
// lucide/Tabler only have a drumstick). Fixed golden-brown fills so it reads as
// "roast chicken" regardless of the surrounding theme.
function ChickenMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true">
      <ellipse cx="32" cy="50" rx="27" ry="6" fill="#E7D2AC" />
      <ellipse cx="32" cy="48.4" rx="27" ry="6" fill="#F6ECD6" />
      <g transform="rotate(-20 20.75 22.5)">
        <rect x="17" y="13.5" width="7.5" height="17" rx="3.75" fill="#C57A2A" />
        <circle cx="20.75" cy="13.5" r="3.8" fill="#F4E6CB" />
      </g>
      <g transform="rotate(20 43.25 22.5)">
        <rect x="39" y="13.5" width="7.5" height="17" rx="3.75" fill="#C57A2A" />
        <circle cx="43.25" cy="13.5" r="3.8" fill="#F4E6CB" />
      </g>
      <ellipse cx="32" cy="37" rx="21" ry="15.5" fill="#B5691E" />
      <ellipse cx="32" cy="34" rx="19" ry="12" fill="#C67C28" />
      <ellipse cx="25" cy="31" rx="8.5" ry="5.5" fill="#D89A45" />
      <circle cx="39" cy="40" r="1.6" fill="#8E4E14" />
      <circle cx="33" cy="43.5" r="1.6" fill="#8E4E14" />
      <circle cx="44" cy="35" r="1.4" fill="#8E4E14" />
      <circle cx="26.5" cy="41" r="1.3" fill="#8E4E14" />
    </svg>
  )
}

// lucide-react v1 removed brand icons (incl. `Github`); inline the GitHub mark.
function GithubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222 0 1.606-.014 2.898-.014 3.293 0 .322.216.694.825.576C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  )
}

interface HeaderProps {
  onToggleSidebar: () => void
}

export function Header({ onToggleSidebar }: HeaderProps) {
  return (
    <header className="flex h-14 items-center border-b bg-background px-3 sm:px-4 gap-2 sm:gap-3 shrink-0">
      <Button
        variant="ghost"
        size="icon"
        onClick={onToggleSidebar}
        aria-label="切換側邊欄"
        className="shrink-0"
      >
        <Menu className="h-5 w-5" />
      </Button>

      <ChickenMark className="h-7 w-7 shrink-0" />

      <span className="flex-1 min-w-0 truncate font-semibold text-base tracking-tight">
        <span className="text-primary">BBQ</span>Rcode Generator
      </span>

      <LoginControl />

      <a
        href="https://github.com/PaynePew/bbqrcode-generator"
        target="_blank"
        rel="noopener noreferrer"
        aria-label="GitHub 儲存庫"
        className="text-muted-foreground hover:text-foreground transition-colors"
      >
        <GithubMark className="h-5 w-5" />
      </a>
    </header>
  )
}
