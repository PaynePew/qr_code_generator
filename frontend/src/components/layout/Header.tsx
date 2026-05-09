import { Github, Menu } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface HeaderProps {
  onToggleSidebar: () => void
}

export function Header({ onToggleSidebar }: HeaderProps) {
  return (
    <header className="flex h-14 items-center border-b bg-background px-4 gap-3 shrink-0">
      <Button
        variant="ghost"
        size="icon"
        onClick={onToggleSidebar}
        aria-label="切換側邊欄"
      >
        <Menu className="h-5 w-5" />
      </Button>

      <span className="flex-1 font-semibold text-base tracking-tight">
        QR Code Generator
      </span>

      <a
        href="https://github.com/PaynePew/qr_code_generator"
        target="_blank"
        rel="noopener noreferrer"
        aria-label="GitHub 儲存庫"
        className="text-muted-foreground hover:text-foreground transition-colors"
      >
        <Github className="h-5 w-5" />
      </a>
    </header>
  )
}
