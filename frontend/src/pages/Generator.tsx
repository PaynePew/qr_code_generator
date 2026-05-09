import { Button } from '@/components/ui/button'

export function Generator() {
  return (
    <div className="flex flex-col gap-4 max-w-lg">
      <h1 className="text-2xl font-bold">QR 碼產生器</h1>
      <p className="text-muted-foreground">
        輸入目標網址並自訂樣式，即可產生專屬的短網址 QR 碼。
      </p>
      <Button disabled>產生 QR 碼</Button>
    </div>
  )
}
