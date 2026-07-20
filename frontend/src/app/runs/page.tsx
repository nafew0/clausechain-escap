import ProtectedRoute from '@/components/ProtectedRoute'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import RunsWorkbench from '@/components/runs/RunsWorkbench'
import { SnapshotBanner } from '@/components/workspace/SnapshotBanner'

export default function RunsPage() {
  return <ProtectedRoute><WorkspaceShell breadcrumbs={[{ label: 'Runs' }]}><SnapshotBanner /><RunsWorkbench /></WorkspaceShell></ProtectedRoute>
}
