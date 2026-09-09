import { useEffect, useState } from 'react'
import { commitBrowserStorage } from './browserStorage'
import {
  getIntelligenceProfile,
  getIntelligenceWork,
  intelligenceStorageEntries,
} from './intelligenceState'
import type { EmergingCase, IntelligenceProfile, IntelligenceWorkItem } from '../types/emerging'

export function useIntelligenceWorkspace() {
  const [profile, setProfileState] = useState(getIntelligenceProfile)
  const [work, setWork] = useState(getIntelligenceWork)
  const [storageMessage, setStorageMessage] = useState<string | null>(null)
  useEffect(() => {
    const refresh = () => {
      setProfileState(getIntelligenceProfile())
      setWork(getIntelligenceWork())
    }
    window.addEventListener('countyiq-investigation-changed', refresh)
    window.addEventListener('storage', refresh)
    return () => {
      window.removeEventListener('countyiq-investigation-changed', refresh)
      window.removeEventListener('storage', refresh)
    }
  }, [])
  function commit(nextProfile: IntelligenceProfile, nextWork: IntelligenceWorkItem[]) {
    try {
      commitBrowserStorage(intelligenceStorageEntries(nextProfile, nextWork))
      setStorageMessage(null)
      window.dispatchEvent(new Event('countyiq-investigation-changed'))
    } catch (error) {
      setStorageMessage(
        error instanceof Error ? error.message : 'Could not save your investigation.',
      )
    }
  }
  return {
    profile,
    work,
    storageMessage,
    setProfile: (value: IntelligenceProfile) => commit(value, getIntelligenceWork()),
    saveCase: (
      item: Pick<EmergingCase, 'case_key' | 'revision'>,
      status: IntelligenceWorkItem['status'],
      note: string,
    ) => {
      const previous = getIntelligenceWork().filter((entry) => entry.case_key !== item.case_key)
      if (previous.length >= 100) {
        setStorageMessage('Your workspace holds 100 cases. Remove a case before saving another.')
        return
      }
      commit(getIntelligenceProfile(), [
        {
          case_key: item.case_key,
          status,
          note: note.slice(0, 4000),
          last_seen_revision: item.revision,
          updated_at: new Date().toISOString(),
        },
        ...previous,
      ])
    },
    removeCase: (key: string) =>
      commit(
        getIntelligenceProfile(),
        getIntelligenceWork().filter((item) => item.case_key !== key),
      ),
  }
}
