export function Dashboard() {
  return (
    <div className="flex flex-col gap-4 max-w-2xl">
      <h1 className="text-2xl font-bold">儀表板</h1>
      <p className="text-muted-foreground">
        您在此瀏覽器建立的所有短網址連結將顯示於此。
      </p>
      <p className="text-sm text-muted-foreground border rounded-md p-4 bg-muted">
        目前尚無連結記錄。請至「產生器」頁面建立您的第一個 QR 碼連結。
      </p>
    </div>
  )
}
