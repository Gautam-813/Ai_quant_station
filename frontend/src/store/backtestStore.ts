import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface BacktestResults {
  metrics: {
    total_return: number
    win_rate: number
    max_drawdown: number
    trades: number
  } | null
  equity_curve: number[] | null
  generated_code: string
  trades?: Array<{
    entry_time: string
    exit_time: string
    direction: string
    entry_price: number
    exit_price: number
    pnl_points: number
    pnl_pct: number
    pnl_dollars: number
    holding_period: number
  }>
}

interface BacktestState {
  selectedPromptId: string
  symbol: string
  timeframe: string
  startDate: string
  endDate: string
  results: BacktestResults | null
  provider: string
  model: string
  lotSize: string

  setSelectedPromptId: (v: string) => void
  setSymbol: (v: string) => void
  setTimeframe: (v: string) => void
  setStartDate: (v: string) => void
  setEndDate: (v: string) => void
  setResults: (v: BacktestResults | null) => void
  setProvider: (v: string) => void
  setModel: (v: string) => void
  setLotSize: (v: string) => void
}

export const useBacktestStore = create<BacktestState>()(
  persist(
    (set) => ({
      selectedPromptId: '',
      symbol: 'XAUUSD',
      timeframe: '15T',
      startDate: '2024-01-01',
      endDate: '2024-12-31',
      results: null,
      provider: 'nvidia',
      model: 'qwen/qwen3.5-122b-a10b',
      lotSize: '0.01',

      setSelectedPromptId: (v) => set({ selectedPromptId: v }),
      setSymbol: (v) => set({ symbol: v }),
      setTimeframe: (v) => set({ timeframe: v }),
      setStartDate: (v) => set({ startDate: v }),
      setEndDate: (v) => set({ endDate: v }),
      setResults: (v) => set({ results: v }),
      setProvider: (v) => set({ provider: v }),
      setModel: (v) => set({ model: v }),
      setLotSize: (v) => set({ lotSize: v }),
    }),
    {
      name: 'backtest-storage',
      partialize: (state) => ({
        selectedPromptId: state.selectedPromptId,
        symbol: state.symbol,
        timeframe: state.timeframe,
        startDate: state.startDate,
        endDate: state.endDate,
        results: state.results,
        provider: state.provider,
        model: state.model,
        lotSize: state.lotSize,
      }),
    }
  )
)
