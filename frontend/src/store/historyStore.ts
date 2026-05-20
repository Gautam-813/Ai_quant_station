import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface HistoryState {
  hours: string

  setHours: (v: string) => void
}

export const useHistoryStore = create<HistoryState>()(
  persist(
    (set) => ({
      hours: '0',

      setHours: (v) => set({ hours: v }),
    }),
    {
      name: 'history-storage',
      partialize: (state) => ({ hours: state.hours }),
    }
  )
)
