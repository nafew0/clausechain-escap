'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { AnimatePresence, MotionConfig, motion } from 'motion/react'
import { LoaderCircle, LogOut, Menu, ShieldCheck, UserRound, X } from 'lucide-react'

import { useAuth } from '@/contexts/AuthContext'
import { PUBLIC_NAV_ITEMS } from '@/lib/navigation'

export default function Navbar() {
  const { user, isAuthenticated, logout, signingOut } = useAuth()
  const [open, setOpen] = useState(false)
  const closeRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
      if (event.key !== 'Tab' || !panelRef.current) return
      const controls = Array.from(panelRef.current.querySelectorAll<HTMLElement>('a[href],button:not([disabled])'))
      if (!controls.length) return
      const first = controls[0]
      const last = controls[controls.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const authActions = (mobile = false) => isAuthenticated ? (
    <>
      <Link href="/dashboard" onClick={mobile ? () => setOpen(false) : undefined} className={mobile ? 'public-mobile-primary' : 'public-header-primary'}>Open workspace</Link>
      <Link href="/profile" onClick={mobile ? () => setOpen(false) : undefined} className={mobile ? 'public-mobile-link' : 'public-header-icon'} aria-label="Profile"><UserRound size={17} /><span className="sr-only">Profile</span></Link>
      {user?.is_superuser ? <Link href="/admin" onClick={mobile ? () => setOpen(false) : undefined} className={mobile ? 'public-mobile-link' : 'public-header-icon'} aria-label="Admin panel"><ShieldCheck size={17} /><span className={mobile ? '' : 'sr-only'}>Admin panel</span></Link> : null}
      <button disabled={signingOut} onClick={() => { setOpen(false); void logout() }} className={mobile ? 'public-mobile-link' : 'public-header-icon'} aria-label={signingOut ? 'Signing out' : 'Sign out'}>{signingOut ? <LoaderCircle className="animate-spin" size={17} /> : <LogOut size={17} />}<span className={mobile ? '' : 'sr-only'}>{signingOut ? 'Signing out' : 'Sign out'}</span></button>
    </>
  ) : (
    <>
      <Link href="/login" onClick={mobile ? () => setOpen(false) : undefined} className={mobile ? 'public-mobile-link' : 'public-header-login'}>Log in</Link>
      <Link href="/register" onClick={mobile ? () => setOpen(false) : undefined} className={mobile ? 'public-mobile-primary' : 'public-header-primary'}>Create account</Link>
    </>
  )

  return (
    <MotionConfig reducedMotion="user"><header className="public-header">
      <div className="public-header-inner">
        <Link href="/" className="public-brand-lockup" aria-label="ClauseChain and United Nations ESCAP home">
          <img src="/branding/logo.svg" alt="ClauseChain" />
          <i aria-hidden="true" />
          <img src="/branding/escap-logo.png" alt="United Nations ESCAP" />
        </Link>
        <nav className="public-header-nav" aria-label="Public navigation">
          {PUBLIC_NAV_ITEMS.map(item => <Link key={item.href} href={item.href}>{item.label}</Link>)}
        </nav>
        <div className="public-header-actions">{authActions()}</div>
        <button className="public-mobile-trigger" aria-label="Open menu" aria-expanded={open} onClick={() => setOpen(true)}><Menu size={21} /></button>
      </div>
      <AnimatePresence>
        {open ? <motion.div className="public-mobile-scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={() => setOpen(false)}>
          <motion.div ref={panelRef} role="dialog" aria-modal="true" aria-label="Public navigation" className="public-mobile-panel" initial={{ x: 30, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 30, opacity: 0 }} transition={{ type: 'spring', stiffness: 360, damping: 34 }} onMouseDown={event => event.stopPropagation()}>
            <div className="public-mobile-heading"><span>Navigate ClauseChain</span><button ref={closeRef} aria-label="Close menu" onClick={() => setOpen(false)}><X size={20} /></button></div>
            <nav>{PUBLIC_NAV_ITEMS.map(item => <Link key={item.href} href={item.href} onClick={() => setOpen(false)}>{item.label}</Link>)}</nav>
            <div className="public-mobile-actions">{authActions(true)}</div>
          </motion.div>
        </motion.div> : null}
      </AnimatePresence>
    </header></MotionConfig>
  )
}
