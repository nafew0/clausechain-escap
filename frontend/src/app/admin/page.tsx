import { redirect } from 'next/navigation'

/** The admin panel holds users and roles; its landing page is the user list. */
export default function AdminPage() {
  redirect('/admin/users')
}
