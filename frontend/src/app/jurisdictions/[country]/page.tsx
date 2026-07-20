import { redirect } from 'next/navigation'

interface Props {
  params: Promise<{ country: string }>
}

export default async function JurisdictionPage({ params }: Props) {
  const { country } = await params
  redirect(`/jurisdictions?view=packs&economy=${encodeURIComponent(country.toUpperCase())}`)
}
