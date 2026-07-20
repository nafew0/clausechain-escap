'use client'
import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  ChevronRight,
  Search, Bell, LogOut, Command,
  ShieldCheck,
  UserRound,
  LoaderCircle,
} from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import { WORKSPACE_NAV_ITEMS, workspaceItemIsActive } from '@/lib/navigation'

interface Crumb { label: string; href?: string }

interface WorkspaceShellProps {
  children: React.ReactNode
  breadcrumbs?: Crumb[]
  contentMode?: 'scroll' | 'contained'
}

export default function WorkspaceShell({ children, breadcrumbs = [], contentMode = 'scroll' }: WorkspaceShellProps) {
  const pathname = usePathname() ?? ''
  const { user, logout, signingOut } = useAuth()
  const [cmdOpen, setCmdOpen] = useState(false)
  const comingSoonItems = WORKSPACE_NAV_ITEMS.filter(item => item.state === 'prototype')
  // Open the group automatically when the current page lives inside it.
  const [comingSoonOpen, setComingSoonOpen] = useState(() =>
    comingSoonItems.some(item => workspaceItemIsActive(pathname, item.href)))

  const initials = user?.email?.slice(0, 2).toUpperCase() ?? 'CC'
  const signOut = () => {
    setCmdOpen(false)
    void logout()
  }

  return (
    <div className="cc-workspace-shell flex h-screen overflow-hidden bg-cc-ink-50" style={{ fontFamily: 'var(--cc-font-display)' }}>
      {/* Sidebar */}
      <aside
        className="cc-sidebar flex flex-col shrink-0 border-r border-cc-ink-200 bg-white overflow-y-auto"
        style={{ height: '100vh', position: 'sticky', top: 0 }}
      >
        {/* Brand */}
        <div className="cc-sidebar-brand flex items-center px-4 pt-5 pb-5">
          <img
            src="/branding/logo.svg"
            alt="ClauseChain"
            loading="eager"
            decoding="async"
            className="h-8 w-auto object-contain"
          />
        </div>

        {/* Nav */}
        <nav className="flex flex-col gap-1 px-3">
          <span className="cc-sidebar-section-label px-2.5 pb-1.5 text-[11px] font-medium tracking-widest uppercase text-cc-ink-500">
            Workspace
          </span>
          {WORKSPACE_NAV_ITEMS.filter(item => item.section === 'workspace' && item.state !== 'prototype').map(({ href, icon: Icon, label }) => {
            const active = workspaceItemIsActive(pathname, href)
            return (
              <Link
                key={href}
                href={href}
                title={label}
                className={`cc-nav-link flex items-center gap-2.5 px-2.5 py-2 rounded-[10px] text-sm font-medium transition-colors ${
                  active
                    ? 'bg-[#EDF5FC] text-[#14548F]'
                    : 'text-cc-ink-700 hover:bg-cc-ink-100 hover:text-cc-ink-900'
                }`}
              >
                <Icon size={16} />
                <span className="cc-nav-text flex-1">{label}</span>
              </Link>
            )
          })}
        </nav>

        {/* Pipeline section */}
        <nav className="flex flex-col gap-1 px-3 mt-2">
          <span className="cc-sidebar-section-label px-2.5 pt-3 pb-1.5 text-[11px] font-medium tracking-widest uppercase text-cc-ink-500">
            Pipeline
          </span>
          {WORKSPACE_NAV_ITEMS.filter(item => item.section === 'pipeline' && item.state !== 'prototype').map(({ href, icon: Icon, label }) => {
            const active = workspaceItemIsActive(pathname, href)
            return (
              <Link
                key={href}
                href={href}
                title={label}
                className={`cc-nav-link flex items-center gap-2.5 px-2.5 py-2 rounded-[10px] text-sm font-medium transition-colors ${
                  active
                    ? 'bg-cc-teal-50 text-cc-teal-600'
                    : 'text-cc-ink-700 hover:bg-cc-ink-100 hover:text-cc-ink-900'
                }`}
              >
                <Icon size={16} />
                <span className="cc-nav-text">{label}</span>
              </Link>
            )
          })}
        </nav>

        {/* Coming soon (prototype screens, collapsed to keep the menu focused) */}
        <nav className="flex flex-col gap-1 px-3 mt-2">
          <button
            type="button"
            onClick={() => setComingSoonOpen(open => !open)}
            aria-expanded={comingSoonOpen}
            className="cc-sidebar-section-label flex items-center gap-1 px-2.5 pt-3 pb-1.5 text-[11px] font-medium tracking-widest uppercase text-cc-ink-500 hover:text-cc-ink-700 transition-colors"
          >
            <ChevronRight
              size={12}
              className={`transition-transform ${comingSoonOpen ? 'rotate-90' : ''}`}
            />
            Coming soon
          </button>
          {comingSoonOpen && comingSoonItems.map(({ href, icon: Icon, label }) => {
            const active = workspaceItemIsActive(pathname, href)
            return (
              <Link
                key={href}
                href={href}
                title={`${label} — prototype sample data`}
                className={`cc-nav-link flex items-center gap-2.5 px-2.5 py-2 rounded-[10px] text-sm font-medium transition-colors ${
                  active
                    ? 'bg-cc-ink-100 text-cc-ink-900'
                    : 'text-cc-ink-500 hover:bg-cc-ink-100 hover:text-cc-ink-700'
                }`}
              >
                <Icon size={16} />
                <span className="cc-nav-text flex-1">{label}</span>
                <span className="cc-nav-state" title="Prototype sample data">P</span>
              </Link>
            )
          })}
        </nav>

        {/* Footer */}
        <div className="cc-sidebar-footer mt-auto px-3 py-4 border-t border-cc-ink-200">
          <div className="flex items-center gap-2.5 px-2.5 py-2">
            <div
              className="w-7 h-7 rounded-full grid place-items-center text-white text-xs font-semibold shrink-0"
              style={{ background: '#1D6FB8' }}
            >
              {initials}
            </div>
            <div className="cc-sidebar-user-copy flex-1 min-w-0">
              <p className="text-sm font-medium text-cc-ink-900 truncate">{signingOut ? 'Signing out…' : (user?.email ?? 'analyst')}</p>
              <p className="text-xs text-cc-ink-500 font-mono">UN Hackathon 2026</p>
            </div>
            <button
              onClick={signOut}
              disabled={signingOut}
              className="p-1.5 rounded-lg text-cc-ink-500 hover:text-cc-ink-900 hover:bg-cc-ink-100 transition-colors"
              title={signingOut ? 'Signing out' : 'Sign out'}
              aria-label={signingOut ? 'Signing out' : 'Sign out'}
            >
              {signingOut ? <LoaderCircle size={14} className="animate-spin" /> : <LogOut size={14} />}
            </button>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Topbar */}
        <header
          className="cc-topbar flex items-center gap-4 h-14 border-b border-cc-ink-200 shrink-0 sticky top-0 z-10"
          style={{ background: 'rgba(255,255,255,0.85)', backdropFilter: 'saturate(180%) blur(12px)' }}
        >
          {/* Breadcrumbs */}
          <nav className="cc-breadcrumbs flex items-center gap-2 text-[13px] text-cc-ink-500 min-w-0 flex-1">
            <Link href="/dashboard" aria-label="ClauseChain dashboard" className="flex items-center shrink-0 opacity-80 hover:opacity-100 transition-opacity">
              <img
                src="/branding/logo.svg"
                alt="ClauseChain"
                loading="eager"
                decoding="async"
                className="h-[1.35rem] w-auto object-contain"
              />
            </Link>
            <span className="h-5 w-px bg-cc-ink-200" aria-hidden="true" />
            <img src="/branding/escap-logo.png" alt="United Nations ESCAP" className="h-5 w-auto object-contain" />
            {breadcrumbs.map((crumb, i) => (
              <span key={i} className="flex items-center gap-1.5 min-w-0">
                <ChevronRight size={12} className="text-cc-ink-300 shrink-0" />
                {crumb.href ? (
                  <Link href={crumb.href} className="hover:text-cc-ink-900 transition-colors truncate">
                    {crumb.label}
                  </Link>
                ) : (
                  <span className="text-cc-ink-900 font-medium truncate">{crumb.label}</span>
                )}
              </span>
            ))}
          </nav>

          {/* Search trigger */}
          <button
            onClick={() => setCmdOpen(true)}
            className="cc-search-trigger flex items-center gap-2.5 px-3 py-1.5 rounded-[10px] bg-cc-ink-100 text-cc-ink-500 text-[13px] border border-transparent hover:bg-cc-ink-50 hover:border-cc-ink-200 transition-colors"
          >
            <Search size={13} />
            <span className="cc-search-label flex-1 text-left">Search clauses, docs…</span>
            <span className="cc-search-kbd flex items-center gap-0.5 text-[11px] font-mono text-cc-ink-600 bg-white border border-cc-ink-200 px-1.5 py-0.5 rounded">
              <Command size={10} />K
            </span>
          </button>

          <button aria-label="Notifications" className="p-2 rounded-lg text-cc-ink-600 hover:bg-cc-ink-100 hover:text-cc-ink-900 transition-colors">
            <Bell size={16} />
          </button>
          {user?.is_superuser ? <Link href="/admin" aria-label="Admin panel" className="p-2 rounded-lg text-cc-ink-600 hover:bg-cc-ink-100 hover:text-cc-ink-900 transition-colors"><ShieldCheck size={16} /></Link> : null}
          <Link href="/profile" aria-label="Profile" className="p-2 rounded-lg text-cc-ink-600 hover:bg-cc-ink-100 hover:text-cc-ink-900 transition-colors">
            <UserRound size={16} />
          </Link>
        </header>

        {/* Page content */}
        <main className={`flex min-h-0 flex-1 flex-col ${contentMode === 'contained' ? 'overflow-hidden' : 'overflow-y-auto'}`}>
          {children}
        </main>
      </div>

      {/* Command palette */}
      {cmdOpen && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh]"
          style={{ background: 'rgba(10,10,11,0.32)', backdropFilter: 'blur(4px)' }}
          onClick={() => setCmdOpen(false)}
        >
          <div
            className="w-full max-w-[640px] bg-white rounded-2xl overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 px-5 py-4 border-b border-cc-ink-200">
              <Search size={18} className="text-cc-ink-500" />
              <input
                autoFocus
                placeholder="Search clauses, jurisdictions, documents…"
                className="flex-1 border-none outline-none text-[17px] text-cc-ink-900 bg-transparent placeholder:text-cc-ink-400"
                onKeyDown={(e) => e.key === 'Escape' && setCmdOpen(false)}
              />
              <kbd className="text-[11px] font-mono text-cc-ink-600 bg-cc-ink-100 px-2 py-1 rounded">ESC</kbd>
            </div>
            <div className="p-2 max-h-[50vh] overflow-y-auto">
              <p className="px-3 py-2.5 text-[11px] font-medium tracking-widest uppercase text-cc-ink-500">Quick Navigation</p>
              {WORKSPACE_NAV_ITEMS.map(({ href, icon: Icon, label }) => (
                <Link
                  key={href}
                  href={href}
                  onClick={() => setCmdOpen(false)}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-[10px] cursor-pointer hover:bg-cc-teal-50 transition-colors"
                >
                  <Icon size={16} className="text-cc-ink-500" />
                  <span className="text-sm text-cc-ink-900">{label}</span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
