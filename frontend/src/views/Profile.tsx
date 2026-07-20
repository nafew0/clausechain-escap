'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { Building2, Camera, CheckCircle2, KeyRound, LoaderCircle, Mail, Phone, ShieldCheck, UserRound } from 'lucide-react'

import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useAuth, type User } from '@/contexts/AuthContext'
import { useSummary } from '@/hooks/workspace'
import { useToast } from '@/hooks/useToast'
import { resolveApiAssetUrl } from '@/services/api'

interface ProfileForm {
  first_name: string
  last_name: string
  email: string
  phone: string
  organization: string
  designation: string
  bio: string
}

const AVATAR_MAX_SIZE = 5 * 1024 * 1024
const AVATAR_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']

function formFromUser(user: User | null): ProfileForm {
  return {
    first_name: user?.first_name ?? '', last_name: user?.last_name ?? '', email: user?.email ?? '',
    phone: user?.phone ?? '', organization: user?.organization ?? '', designation: user?.designation ?? '', bio: user?.bio ?? '',
  }
}

function initials(user: User | null, form: ProfileForm) {
  const value = `${form.first_name[0] ?? ''}${form.last_name[0] ?? ''}`.trim()
  return value.toUpperCase() || user?.username.slice(0, 2).toUpperCase() || 'CC'
}

function roleLabel(role: string) {
  if (role === 'admin') return 'Review administrator'
  return role.replace('_reviewer', ' reviewer').replace(/^./, value => value.toUpperCase())
}

export default function Profile() {
  const { user, updateUser } = useAuth()
  const summary = useSummary()
  const { toast } = useToast()
  const inputRef = useRef<HTMLInputElement>(null)
  const [form, setForm] = useState(() => formFromUser(user))
  const [avatar, setAvatar] = useState(() => resolveApiAssetUrl(user?.avatar))
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    // Auth refreshes can replace the user object after the first client render.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setForm(formFromUser(user))
    setAvatar(resolveApiAssetUrl(user?.avatar))
  }, [user])

  const updateField = (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setForm(current => ({ ...current, [event.target.name]: event.target.value }))
    setSaved(false)
  }

  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    setSaving(true)
    const result = await updateUser({
      first_name: form.first_name.trim(), last_name: form.last_name.trim(), phone: form.phone.trim(),
      organization: form.organization.trim(), designation: form.designation.trim(), bio: form.bio.trim(),
    })
    setSaving(false)
    if (result.success) {
      setSaved(true)
      toast({ title: 'Profile saved', description: 'Your reviewer identity is up to date.', variant: 'success' })
    } else toast({ title: 'Profile could not be saved', description: result.error, variant: 'error' })
  }

  const uploadAvatar = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    if (!AVATAR_TYPES.includes(file.type) || file.size > AVATAR_MAX_SIZE) {
      toast({ title: 'Unsupported profile image', description: 'Use JPG, PNG, WEBP or GIF up to 5 MB.', variant: 'error' })
      event.target.value = ''
      return
    }
    const temporaryUrl = URL.createObjectURL(file)
    const previous = avatar
    setAvatar(temporaryUrl)
    setUploading(true)
    const payload = new FormData()
    payload.append('avatar', file)
    const result = await updateUser(payload)
    URL.revokeObjectURL(temporaryUrl)
    setUploading(false)
    setAvatar(result.success ? resolveApiAssetUrl(result.user?.avatar) : previous)
    toast(result.success
      ? { title: 'Photo updated', description: 'Your reviewer avatar has been saved.', variant: 'success' }
      : { title: 'Photo upload failed', description: result.error, variant: 'error' })
    event.target.value = ''
  }

  const fields = [
    ['first_name', 'First name', UserRound, 'Given name'], ['last_name', 'Last name', UserRound, 'Family name'],
    ['email', 'Email', Mail, 'Email address'], ['phone', 'Phone', Phone, '+880…'],
    ['organization', 'Organization', Building2, 'Organization'], ['designation', 'Designation', ShieldCheck, 'Legal reviewer'],
  ] as const
  const displayName = `${form.first_name} ${form.last_name}`.trim() || user?.username || 'Reviewer'
  const roles = summary.data?.reviewer_roles ?? []

  return <WorkspaceShell breadcrumbs={[{ label: 'Profile' }]}>
    <div className="cc-page profile-workspace">
      <div className="cc-page-header"><div><span className="review-eyebrow">Reviewer identity</span><h1 className="cc-page-title text-[32px] mt-3">Profile and access</h1><p className="text-cc-ink-500 mt-1.5">The identity shown on append-only legal review decisions.</p></div>{saved ? <div className="profile-saved"><CheckCircle2 size={16} /> Saved</div> : null}</div>
      <div className="profile-layout">
        <aside className="truth-data-card profile-identity" data-data-card>
          <input ref={inputRef} className="sr-only" type="file" accept={AVATAR_TYPES.join(',')} onChange={uploadAvatar} />
          <button className="profile-avatar-button" onClick={() => inputRef.current?.click()} disabled={uploading} aria-label="Change profile photo">
            <Avatar className="profile-avatar"><AvatarImage src={avatar} alt={`${displayName} avatar`} /><AvatarFallback>{initials(user, form)}</AvatarFallback></Avatar>
            <span>{uploading ? <LoaderCircle className="animate-spin" size={16} /> : <Camera size={16} />}</span>
          </button>
          <h2>{displayName}</h2><p>@{user?.username}</p><small>Member since {user?.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}</small>
          <section><span>Review authority</span>{summary.isPending ? <p>Loading roles…</p> : roles.length ? <div className="profile-roles">{roles.map(role => <strong key={role}>{roleLabel(role)}</strong>)}</div> : <p>Read-only access. No review role assigned.</p>}</section>
          <Link className="profile-security-link" href="/forgot-password"><KeyRound size={16} /><span><strong>Reset password</strong><small>Start the secure email flow</small></span></Link>
        </aside>
        <form className="truth-data-card profile-form" data-data-card onSubmit={save}>
          <header><div><span>ACCOUNT DETAILS</span><h2>Contact and professional information</h2></div></header>
          <div className="profile-fields">{fields.map(([name, label, Icon, placeholder]) => <label key={name}><Label htmlFor={name}>{label}</Label><span><Icon size={15} /><Input id={name} name={name} value={form[name]} onChange={updateField} placeholder={placeholder} readOnly={name === 'email'} /></span>{name === 'email' ? <small>Email changes require a separate verification flow.</small> : null}</label>)}</div>
          <label className="profile-bio"><Label htmlFor="bio">Biography</Label><Textarea id="bio" name="bio" value={form.bio} onChange={updateField} placeholder="Your legal, policy or technical review background." /></label>
          <footer><p>Changes are used for reviewer attribution on future decisions.</p><Button type="submit" disabled={saving || uploading}>{saving ? <><LoaderCircle className="animate-spin" size={16} /> Saving…</> : 'Save profile'}</Button></footer>
        </form>
      </div>
    </div>
  </WorkspaceShell>
}
