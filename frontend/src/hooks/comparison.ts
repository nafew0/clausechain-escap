'use client'

import { useQuery } from '@tanstack/react-query'

import { getComparison } from '@/services/comparison'

export function useComparison(economy?: string, pillar?: string) {
  return useQuery({
    queryKey: ['workspace', 'comparison', economy ?? '', pillar ?? ''],
    queryFn: () => getComparison(economy, pillar),
  })
}
