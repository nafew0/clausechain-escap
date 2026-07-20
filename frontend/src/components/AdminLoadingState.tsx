export default function AdminLoadingState({
  message = 'Loading admin workspace...',
}: {
  message?: string
}) {
  return (
    <div className="theme-app-gradient flex min-h-screen items-center justify-center">
      <div className="theme-panel rounded-2xl px-5 py-4 text-sm font-medium text-muted-foreground">
        {message}
      </div>
    </div>
  )
}
