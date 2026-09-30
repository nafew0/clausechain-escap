'use client'
import { useMemo } from 'react'
import { PageLoader } from '@/components/clausechain/PageLoader'
import { useRouter, usePathname, useSearchParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import type { ColumnDef } from '@tanstack/react-table'
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { CustomSelect } from '@/components/ui/custom-select'
import { Input } from '@/components/ui/input'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { getAdminUsers } from '@/services/admin'
import { ROLE_BADGE, ROLE_LABELS, type AccountRole } from '@/lib/roles'

import { formatDateTime } from './admin-helpers'

interface UserRow {
  id: string
  username: string
  email: string
  role: AccountRole
  is_active: boolean
  created_at: string
}

function updateSearchParams(
  searchParams: string,
  patch: Record<string, string>,
  pathname: string
) {
  const next = new URLSearchParams(searchParams)
  Object.entries(patch).forEach(([key, value]) => {
    if (!value) {
      next.delete(key)
    } else {
      next.set(key, value)
    }
  })
  if (patch.page === undefined) {
    next.set('page', '1')
  }
  window.history.replaceState(null, '', `${pathname}?${next.toString()}`)
}

export default function AdminUsers() {
  const router = useRouter()
  const pathname = usePathname() ?? ''
  const searchParams = useSearchParams()
  const searchParamString = searchParams?.toString() ?? ''
  const params = useMemo(
    () => {
      const next = new URLSearchParams(searchParamString)
      return {
        page: next.get('page') || '1',
        search: next.get('search') || '',
        role: next.get('role') || '',
        is_active: next.get('is_active') || '',
        ordering: next.get('ordering') || '-created_at',
      }
    },
    [searchParamString]
  )

  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-users', params],
    queryFn: () => getAdminUsers(params),
  })

  const columns = useMemo<ColumnDef<UserRow>[]>(
    () => [
      {
        accessorKey: 'username',
        header: 'User',
        cell: ({ row }) => (
          <div>
            <p className="font-medium text-foreground">{row.original.username}</p>
            <p className="text-xs text-muted-foreground">{row.original.email}</p>
          </div>
        ),
      },
      {
        accessorKey: 'role',
        header: 'Role',
        cell: ({ row }) => <Badge variant={ROLE_BADGE[row.original.role] ?? 'secondary'}>{ROLE_LABELS[row.original.role] ?? row.original.role}</Badge>,
      },
      {
        accessorKey: 'is_active',
        header: 'Status',
        cell: ({ row }) => (
          <Badge variant={row.original.is_active ? 'success' : 'danger'}>
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        ),
      },
      {
        accessorKey: 'created_at',
        header: 'Joined',
        cell: ({ row }) => formatDateTime(row.original.created_at, { hour: undefined, minute: undefined }),
      },
    ],
    []
  )

  const table = useReactTable({
    data: (data?.results || []) as UserRow[],
    columns,
    getCoreRowModel: getCoreRowModel(),
  })

  const roleOptions = [
    { label: 'All roles', value: '' },
    ...(Object.entries(ROLE_LABELS).map(([value, label]) => ({ label, value }))),
  ]

  if (isLoading) {
    return <PageLoader label="Loading users" />
  }

  if (error) {
    return <div className="theme-panel rounded-[1.8rem] p-6 text-sm text-rose-600">ClauseChain could not load users right now.</div>
  }

  const currentPage = Number(params.page || 1)
  const totalPages = Math.max(1, Math.ceil((data?.count || 0) / 20))

  return (
    <Card className="theme-panel rounded-[1.8rem] border-0">
      <CardHeader className="gap-4">
        <div>
          <CardTitle>Users</CardTitle>
          <CardDescription>Search ClauseChain accounts, see each person&apos;s role, and open one to change it.</CardDescription>
        </div>
        <div className="grid gap-3 lg:grid-cols-[1.4fr_repeat(3,minmax(0,0.8fr))]">
          <Input
            placeholder="Search username or email"
            value={params.search}
            onChange={(event) =>
              updateSearchParams(searchParamString, { search: event.target.value }, pathname)
            }
          />
          <CustomSelect
            value={params.role}
            onChange={(value) => updateSearchParams(searchParamString, { role: String(value) }, pathname)}
            options={roleOptions}
          />
          <CustomSelect
            value={params.is_active}
            onChange={(value) => updateSearchParams(searchParamString, { is_active: String(value) }, pathname)}
            options={[
              { label: 'All statuses', value: '' },
              { label: 'Active', value: 'true' },
              { label: 'Inactive', value: 'false' },
            ]}
          />
          <CustomSelect
            value={params.ordering}
            onChange={(value) => updateSearchParams(searchParamString, { ordering: String(value) }, pathname)}
            options={[
              { label: 'Newest first', value: '-created_at' },
              { label: 'Oldest first', value: 'created_at' },
              { label: 'Username A-Z', value: 'username' },
              { label: 'Username Z-A', value: '-username' },
            ]}
          />
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th key={header.id} className="pb-3 pr-4">
                      {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className="cursor-pointer border-t border-[rgb(var(--theme-border-rgb)/0.7)] transition hover:bg-white/50"
                  onClick={() => router.push(`/admin/users/${row.original.id}`)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="py-3 pr-4 align-top">
                      {cell.column.columnDef.cell
                        ? flexRender(cell.column.columnDef.cell, cell.getContext())
                        : String(cell.getValue())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            Showing page {currentPage} of {totalPages}.
          </p>
          <div className="flex gap-3">
            <Button
              variant="outline"
              className="rounded-xl"
              disabled={currentPage <= 1}
              onClick={() =>
                updateSearchParams(searchParamString, { page: String(currentPage - 1) }, pathname)
              }
            >
              Previous
            </Button>
            <Button
              variant="outline"
              className="rounded-xl"
              disabled={currentPage >= totalPages}
              onClick={() =>
                updateSearchParams(searchParamString, { page: String(currentPage + 1) }, pathname)
              }
            >
              Next
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
