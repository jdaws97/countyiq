import type { AssemblageCluster, DistressedParcel } from './api'

declare global {
  interface Window {
    __assemblageCache?: Record<string, AssemblageCluster[]>
    __distressedCache?: Record<string, DistressedParcel[]>
  }
}

export {}
