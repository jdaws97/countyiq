import { createContext, useContext } from 'react'
import type { EvidenceItem } from '../types/api'

export const SourceContext = createContext<(items: EvidenceItem[], index?: number) => void>(
  () => {},
)

export function useSourceViewer() {
  return useContext(SourceContext)
}
