'use client'
import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import { Check } from 'lucide-react'

import { PageLoader } from '@/components/clausechain/PageLoader'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { ROLE_BADGE } from '@/lib/roles'
import { getAdminRoles } from '@/services/admin'

export default function AdminRoles() {
  const { data, isLoading, error } = useQuery({ queryKey: ['admin-roles'], queryFn: getAdminRoles })

  if (isLoading) {
    return <PageLoader label="Loading roles" />
  }

  if (error || !data) {
    return <div className="theme-panel rounded-[1.8rem] p-6 text-sm text-rose-600">ClauseChain could not load roles right now.</div>
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Every account holds one role. New sign-ups start as Viewer; change a role from the user&apos;s page.
      </p>
      <div className="grid gap-6 xl:grid-cols-3">
        {data.roles.map((role) => (
          <Card key={role.key} className="theme-panel rounded-[1.8rem] border-0">
            <CardHeader className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle>{role.label}</CardTitle>
                <Badge variant={ROLE_BADGE[role.key] ?? 'secondary'}>
                  {role.user_count} {role.user_count === 1 ? 'user' : 'users'}
                </Badge>
                {role.default_for_new_users ? <Badge variant="outline">Default for new accounts</Badge> : null}
              </div>
              <CardDescription>{role.description}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <ul className="space-y-2">
                {role.permissions.map((permission) => (
                  <li key={permission} className="flex items-start gap-2 text-sm text-foreground">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                    {permission}
                  </li>
                ))}
              </ul>
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Members</p>
                {role.members.length ? (
                  <ul className="space-y-2">
                    {role.members.map((member) => (
                      <li key={member.id}>
                        <Link
                          href={`/admin/users/${member.id}`}
                          className="flex items-center justify-between gap-3 rounded-[1rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 px-3 py-2 transition hover:bg-white"
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-medium text-foreground">{member.full_name || member.username}</span>
                            <span className="block truncate text-xs text-muted-foreground">{member.email || member.username}</span>
                          </span>
                          {member.is_active ? null : <Badge variant="danger">Inactive</Badge>}
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">No accounts hold this role.</p>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
