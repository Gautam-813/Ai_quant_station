import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Mode = 'backtest' | 'analysis'
type Status = 'pending' | 'running' | 'completed' | 'failed'

interface Metrics {
  total_return_pct: number
  sharpe_ratio: number
  max_drawdown_pct: number
  win_rate_pct: number
  profit_factor: number
  num_trades: number
  final_equity: number
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  execution_output?: string
  execution_charts?: any[]
  execution_tables?: any[]
}

interface LabResult {
  id: number
  mode: Mode
  symbol: string
  status: Status
  equity_curve?: { time: string; balance: number }[]
  metrics?: Metrics
  analysis?: any
  ai_report: string
  chat_history: ChatMessage[]
}

interface HistoricalLabState {
  mode: Mode
  symbol: string
  startDate: string
  endDate: string
  timeframe: string
  capital: string
  leverage: string
  includeSpread: boolean
  includeCommission: boolean
  prompt: string
  provider: string
  model: string
  backtestResult: LabResult | null
  analysisResult: LabResult | null

  setMode: (v: Mode) => void
  setSymbol: (v: string) => void
  setStartDate: (v: string) => void
  setEndDate: (v: string) => void
  setTimeframe: (v: string) => void
  setCapital: (v: string) => void
  setLeverage: (v: string) => void
  setIncludeSpread: (v: boolean) => void
  setIncludeCommission: (v: boolean) => void
  setPrompt: (v: string) => void
  setProvider: (v: string) => void
  setModel: (v: string) => void
  setBacktestResult: (v: LabResult | null) => void
  setAnalysisResult: (v: LabResult | null) => void
}

export const useHistoricalLabStore = create<HistoricalLabState>()(
  persist(
    (set) => ({
      mode: 'backtest',
      symbol: 'XAUUSD',
      startDate: '2015-01-01',
      endDate: '2025-12-31',
      timeframe: '1T',
      capital: '10000',
      leverage: '100',
      includeSpread: false,
      includeCommission: false,
      prompt: '',
      provider: 'nvidia',
      model: 'qwen/qwen3.5-122b-a10b',
      backtestResult: null,
      analysisResult: null,

      setMode: (v) => set({ mode: v }),
      setSymbol: (v) => set({ symbol: v }),
      setStartDate: (v) => set({ startDate: v }),
      setEndDate: (v) => set({ endDate: v }),
      setTimeframe: (v) => set({ timeframe: v }),
      setCapital: (v) => set({ capital: v }),
      setLeverage: (v) => set({ leverage: v }),
      setIncludeSpread: (v) => set({ includeSpread: v }),
      setIncludeCommission: (v) => set({ includeCommission: v }),
      setPrompt: (v) => set({ prompt: v }),
      setProvider: (v) => set({ provider: v }),
      setModel: (v) => set({ model: v }),
      setBacktestResult: (v) => set({ backtestResult: v }),
      setAnalysisResult: (v) => set({ analysisResult: v }),
    }),
    {
      name: 'historical-lab-storage',
      partialize: (state) => ({
        mode: state.mode,
        symbol: state.symbol,
        startDate: state.startDate,
        endDate: state.endDate,
        timeframe: state.timeframe,
        capital: state.capital,
        leverage: state.leverage,
        includeSpread: state.includeSpread,
        includeCommission: state.includeCommission,
        prompt: state.prompt,
        provider: state.provider,
        model: state.model,
        backtestResult: state.backtestResult,
        analysisResult: state.analysisResult,
      }),
    }
  )
)
