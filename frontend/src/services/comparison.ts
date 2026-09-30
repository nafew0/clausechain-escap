import api from '@/services/api'
import type { ComparisonResponse } from '@/types/comparison'

export async function getComparison(economy?: string, pillar?: string): Promise<ComparisonResponse> {
  const { data } = await api.get<ComparisonResponse>('/workspace/comparison/', {
    params: economy && pillar ? { economy, pillar } : {},
  })
  return data
}

export async function downloadComparison(economy: string, pillar: string) {
  const response = await api.get<Blob>('/workspace/comparison/export/', {
    params: { economy, pillar },
    responseType: 'blob',
  })
  const disposition = String(response.headers['content-disposition'] ?? '')
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'clausechain_engine_comparison.csv'
  const href = URL.createObjectURL(response.data)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = name
  anchor.click()
  URL.revokeObjectURL(href)
}
