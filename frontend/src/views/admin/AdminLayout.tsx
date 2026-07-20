'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  ArrowLeft,
  CreditCard,
  LayoutDashboard,
  Settings2,
  ShieldCheck,
  Users,
} from 'lucide-react'

import { useAuth } from '@/contexts/AuthContext'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { to: '/admin', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/admin/users', label: 'Users', icon: Users },
  { to: '/admin/payments', label: 'Payments', icon: CreditCard },
  { to: '/admin/settings', label: 'Settings', icon: Settings2 },
]

function getAdminTitle(pathname: string) {
  if (pathname.startsWith('/admin/users/')) return 'User detail'
  if (pathname.startsWith('/admin/users')) return 'User management'
  if (pathname.startsWith('/admin/payments')) return 'Payments'
  if (pathname.startsWith('/admin/settings')) return 'Platform settings'
  return 'Admin overview'
}

function getPlansUrl() {
  const base = (process.env.NEXT_PUBLIC_DJANGO_ADMIN_URL?.trim() || 'http://localhost:8000/admin').replace(/\/+$/, '')
  return `${base}/subscriptions/plan/`
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const pathname = usePathname()
  const pageTitle = getAdminTitle(pathname ?? '')
  const plansUrl = getPlansUrl()

  return (
    <div className="theme-app-gradient min-h-[calc(100vh-4rem)] px-4 py-6 sm:px-5">
      <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)] lg:items-start">
        <aside className="theme-panel rounded-[2rem] p-5 lg:sticky lg:top-20 lg:h-[calc(100vh-6rem)]">
          <div className="rounded-[1.5rem] border border-[rgb(var(--theme-border-rgb)/0.8)] bg-[rgb(var(--theme-primary-soft-rgb)/0.72)] p-4">
            <div className="flex items-center gap-3">
              <div className="theme-icon-primary flex h-11 w-11 items-center justify-center rounded-2xl">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                  reactdjango
                </p>
                <p className="text-lg font-semibold text-foreground">Admin panel</p>
              </div>
            </div>
            <p className="mt-3 text-sm text-muted-foreground">
              {user?.email || 'Authorized workspace'}
            </p>
          </div>

          <nav className="mt-6 space-y-2">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon
              const isActive = item.end ? pathname === item.to : (pathname?.startsWith(item.to) ?? false)
              return (
                <Link
                  key={item.to}
                  href={item.to}
                  className={cn(
                    'flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition',
                    isActive
                      ? 'bg-[rgb(var(--theme-primary-soft-rgb)/0.9)] text-[rgb(var(--theme-primary-ink-rgb))]'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </Link>
              )
            })}
          </nav>

          <div className="mt-6 space-y-3 rounded-[1.5rem] border border-dashed border-[rgb(var(--theme-border-rgb)/0.82)] p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Quick links
            </p>
            <a
              href={plansUrl}
              target="_blank"
              rel="noreferrer"
              className="block rounded-xl bg-white/80 px-3 py-2 text-sm font-medium text-foreground transition hover:bg-white"
            >
              Plans in Django Admin
            </a>
            <Button asChild variant="outline" className="w-full rounded-xl">
              <Link href="/dashboard">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to app
              </Link>
            </Button>
          </div>
        </aside>

        <section className="min-w-0 xl:max-w-6xl">
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                Operations workspace
              </p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-foreground">
                {pageTitle}
              </h1>
            </div>
          </div>
          {children}
        </section>
      </div>
    </div>
  )
}
