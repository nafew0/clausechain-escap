import AdminShell from '@/components/AdminShell'

export default function AdminLayoutShim({ children }: { children: React.ReactNode }) {
  return <AdminShell>{children}</AdminShell>
}
