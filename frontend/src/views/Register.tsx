'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { AlertCircle, ArrowRight, CheckCircle2, LoaderCircle, MailCheck, RotateCw } from 'lucide-react'

import PublicAuthShell from '@/components/auth/PublicAuthShell'
import SocialLoginButtons from '@/components/auth/SocialLoginButtons'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/hooks/useToast'
import { getSignupChallenge } from '@/services/auth'
import { getSafeRedirect } from '@/utils/redirects'

interface SignupChallenge {
  captcha_enabled: boolean
  captcha_id: string
  captcha_prompt: string
  registration_token: string
  minimum_submit_seconds: number
}

export default function Register() {
  const [form, setForm] = useState({ username: '', email: '', password: '', password2: '', first_name: '', last_name: '', captcha_answer: '', company_website: '' })
  const [challenge, setChallenge] = useState<SignupChallenge | null>(null)
  const [challengeLoading, setChallengeLoading] = useState(true)
  const [challengeError, setChallengeError] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [verification, setVerification] = useState<{ emailHint: string; identifier: string } | null>(null)
  const [resending, setResending] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const { register, resendVerificationEmail, isAuthenticated, loading: authLoading } = useAuth()
  const router = useRouter()
  const params = useSearchParams() ?? new URLSearchParams()
  const redirectTo = getSafeRedirect(params.get('redirect'))
  const { toast } = useToast()

  const loadChallenge = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true); else setChallengeLoading(true)
    setChallengeError('')
    try {
      const result = await getSignupChallenge()
      setChallenge(result); setForm(current => ({ ...current, captcha_answer: '' }))
    } catch { setChallenge(null); setChallengeError('Signup protection could not be loaded. Try again.') }
    finally { setRefreshing(false); setChallengeLoading(false) }
  }, [])

  useEffect(() => { if (isAuthenticated) router.replace('/dashboard') }, [isAuthenticated, router])
  useEffect(() => { if (!isAuthenticated) { const timer = window.setTimeout(() => void loadChallenge(), 0); return () => window.clearTimeout(timer) } }, [isAuthenticated, loadChallenge])
  useEffect(() => {
    if (cooldown <= 0) return
    const timer = window.setInterval(() => setCooldown(value => Math.max(0, value - 1)), 1000)
    return () => window.clearInterval(timer)
  }, [cooldown])

  if (isAuthenticated) return null

  const change = (event: React.ChangeEvent<HTMLInputElement>) => { setForm(current => ({ ...current, [event.target.name]: event.target.value })); setError('') }
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setError('')
    if (!challenge?.registration_token) { setError('Registration protection is not ready. Reload it and try again.'); return }
    if (form.password !== form.password2) { setError('Passwords do not match.'); return }
    setSubmitting(true)
    const result = await register({ ...form, captcha_id: challenge.captcha_id, registration_token: challenge.registration_token })
    setSubmitting(false)
    if (!result.success) { setError(result.error ?? 'Registration failed.'); await loadChallenge(true); return }
    if (result.emailVerificationRequired) { setVerification({ emailHint: result.emailHint ?? '', identifier: form.email.trim() }); setCooldown(120); return }
    router.push(redirectTo)
  }
  const resend = async () => {
    if (!verification?.identifier || resending || cooldown) return
    setResending(true); const result = await resendVerificationEmail(verification.identifier); setResending(false)
    if (result.success) { setCooldown(120); toast({ title: 'Verification email requested', description: result.message, variant: 'success' }) }
    else toast({ title: 'Verification email unavailable', description: result.error, variant: 'error' })
  }

  return <PublicAuthShell mode="register"><div className="public-auth-form register">
    {verification ? <div className="public-verification-state"><MailCheck /><span className="public-form-kicker">EMAIL VERIFICATION</span><h2>Check your inbox</h2><p>Your account is ready. Verify your email before signing in.{verification.emailHint ? ` The first link was sent to ${verification.emailHint}.` : ''}</p><Button onClick={resend} disabled={resending || cooldown > 0}>{resending ? 'Requesting…' : cooldown ? `Resend in ${cooldown}s` : 'Resend verification email'}</Button><Link href="/login">Back to sign in</Link></div> : <>
      <span className="public-form-kicker">OPEN REGISTRATION</span><h2>Create a reviewer account</h2><p>One account identity, attached to every decision.</p>
      {authLoading ? <div className="public-auth-loading"><LoaderCircle className="animate-spin" /> Checking your secure session…</div> : <form onSubmit={submit} className="public-register-form">
        {error ? <div className="public-auth-notice error"><AlertCircle />{error}</div> : null}
        <fieldset><legend>Identity</legend><div className="public-field-grid"><label><span>First name</span><input name="first_name" autoComplete="given-name" value={form.first_name} onChange={change} placeholder="First name" /></label><label><span>Last name</span><input name="last_name" autoComplete="family-name" value={form.last_name} onChange={change} placeholder="Last name" /></label></div><label><span>Email</span><input name="email" type="email" autoComplete="email" value={form.email} onChange={change} placeholder="you@example.com" required /></label></fieldset>
        <fieldset><legend>Credentials</legend><label><span>Username</span><input name="username" autoComplete="username" value={form.username} onChange={change} placeholder="Choose a username" required /></label><div className="public-field-grid"><label><span>Password</span><input name="password" type="password" autoComplete="new-password" value={form.password} onChange={change} placeholder="Create password" required /></label><label><span>Confirm password</span><input name="password2" type="password" autoComplete="new-password" value={form.password2} onChange={change} placeholder="Repeat password" required /></label></div></fieldset>
        <input className="public-honeypot" aria-hidden="true" tabIndex={-1} name="company_website" autoComplete="off" value={form.company_website} onChange={change} />
        <fieldset><legend>Human verification</legend>{challengeLoading ? <div className="public-auth-loading compact"><LoaderCircle className="animate-spin" /> Preparing signup protection…</div> : challengeError ? <div className="public-auth-notice error"><AlertCircle /><span>{challengeError}<Button type="button" variant="outline" onClick={() => void loadChallenge()}>Retry</Button></span></div> : challenge?.captcha_enabled ? <div className="public-captcha"><div><span>Human check</span><strong>{challenge.captcha_prompt}</strong></div><Button type="button" variant="outline" onClick={() => void loadChallenge(true)} disabled={refreshing}>{refreshing ? <LoaderCircle className="animate-spin" /> : <RotateCw />} Refresh</Button><label><span>Answer</span><input name="captcha_answer" inputMode="numeric" autoComplete="off" value={form.captcha_answer} onChange={change} required /></label></div> : <div className="public-auth-notice success"><CheckCircle2 />Signup protection is ready.</div>}</fieldset>
        <button className="public-auth-submit" disabled={submitting || challengeLoading || !challenge?.registration_token}>{submitting ? <><LoaderCircle className="animate-spin" /> Creating account…</> : <>Create account <ArrowRight /></>}</button>
      </form>}
      {!authLoading ? <><div className="public-auth-social"><span>Or continue with</span><SocialLoginButtons nextPath={redirectTo} /></div><p className="public-auth-switch">Already registered? <Link href="/login">Sign in</Link></p></> : null}
    </>}
  </div></PublicAuthShell>
}
