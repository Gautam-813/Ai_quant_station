import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface TerminalState {
  selectedSymbol: string
  orderType: string
  direction: string
  volume: string
  price: string
  sl: string
  tp: string

  setSelectedSymbol: (v: string) => void
  setOrderType: (v: string) => void
  setDirection: (v: string) => void
  setVolume: (v: string) => void
  setPrice: (v: string) => void
  setSl: (v: string) => void
  setTp: (v: string) => void
  clearOrder: () => void
}

export const useTerminalStore = create<TerminalState>()(
  persist(
    (set) => ({
      selectedSymbol: 'XAUUSD',
      orderType: 'market',
      direction: 'BUY',
      volume: '0.1',
      price: '',
      sl: '',
      tp: '',

      setSelectedSymbol: (v) => set({ selectedSymbol: v }),
      setOrderType: (v) => set({ orderType: v }),
      setDirection: (v) => set({ direction: v }),
      setVolume: (v) => set({ volume: v }),
      setPrice: (v) => set({ price: v }),
      setSl: (v) => set({ sl: v }),
      setTp: (v) => set({ tp: v }),
      clearOrder: () => set({ price: '', sl: '', tp: '' }),
    }),
    {
      name: 'terminal-storage',
      partialize: (state) => ({
        selectedSymbol: state.selectedSymbol,
        orderType: state.orderType,
        direction: state.direction,
        volume: state.volume,
      }),
    }
  )
)
