import { useFetchJson } from './useFetchJson'
import type { CountyMetadata } from '../types/api'

const FALLBACK: CountyMetadata = {
  county_key: 'york',
  county_name: 'York County',
  state: 'PA',
  product_stage: 'alpha',
}

export function useCountyMeta(): CountyMetadata {
  const { data } = useFetchJson<CountyMetadata>('/api/meta')
  return data ?? FALLBACK
}
