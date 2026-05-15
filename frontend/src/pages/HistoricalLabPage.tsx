import React, { useState, useRef, useEffect } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar
} from 'recharts'
import {
  Play, AlertTriangle, Zap, BrainCircuit, Settings2,
  TrendingUp, History as HistoryIcon, FlaskConical, BarChartHorizontal,
  Send, User as UserIcon, Bot, Loader2
} from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

type Mode = 'backtest' | 'analysis'
type Status = 'pending' | 'running' | 'completed' | 'failed'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

interface Metrics {
  total_return_pct: number
  sharpe_ratio: number
  max_drawdown_pct: number
  win_rate_pct: number
  profit_factor: number
  num_trades: number
  final_equity: number
}

interface LabResult {
  id: number
  mode: Mode
  symbol: string
  status: Status
  equity_curve?: { time: string; balance: number }[]
  metrics?: Metrics
  analysis?: {
    hourly_volatility: { hour_utc: number; avg_range: number }[]
    day_of_week_volatility: { day: string; avg_range: number }[]
    stats: Record<string, any>
  }
  ai_report: string
  chat_history: ChatMessage[]
}

const SYMBOLS = ['XAUUSD', 'BTCUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'XAGUSD']
const TIMEFRAMES = [{ value: '1T', label: '1 Minute' }, { value: '5T', label: '5 Minutes' }, { value: '1H', label: '1 Hour' }]
const LEVERAGES = ['1', '10', '30', '50', '100', '200', '500']

const MetricCard = ({ label, value, sub, icon: Icon, color }: any) => (
  <Card className="bg-card/60 border-border/50">
    <CardContent className="p-4 space-y-1">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground uppercase tracking-wider">{label}</p>
        <Icon className={`w-4 h-4 ${color}`} />
      </div>
      <h3 className={`text-2xl font-bold font-heading ${color}`}>{value}</h3>
      {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
    </CardContent>
  </Card>
)

export default function HistoricalLabPage() {
  const [mode, setMode] = useState<Mode>('backtest')
  const [symbol, setSymbol] = useState('XAUUSD')
  const [startDate, setStartDate] = useState('2015-01-01')
  const [endDate, setEndDate] = useState('2025-12-31')
  const [timeframe, setTimeframe] = useState('1T')
  const [capital, setCapital] = useState('10000')
  const [leverage, setLeverage] = useState('100')
  const [includeSpread, setIncludeSpread] = useState(false)
  const [includeCommission, setIncludeCommission] = useState(false)
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<LabResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  
  // Chat specific state
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  // Polling for status
  useEffect(() => {
    let interval: any = null;
    
    if (result && (result.status === 'pending' || result.status === 'running')) {
      interval = setInterval(async () => {
        try {
          const token = localStorage.getItem('access_token')
          const res = await fetch(`${API_BASE}/historical-lab/status/${result.id}`, {
            headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) }
          })
          if (res.ok) {
            const data = await res.json()
            setResult(data)
            if (data.status === 'completed' || data.status === 'failed') {
              setLoading(false)
              if (data.status === 'failed') setError('Processing failed. Please check parameters.')
            }
          }
        } catch (e) {
          console.error("Polling error", e)
        }
      }, 2000)
    }
    
    return () => { if (interval) clearInterval(interval) }
  }, [result?.id, result?.status])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [result?.chat_history])

  const handleRun = async () => {
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch(`${API_BASE}/historical-lab/run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          mode, symbol, start_date: startDate, end_date: endDate,
          timeframe, prompt, initial_capital: parseFloat(capital),
          leverage: parseFloat(leverage), include_spread: includeSpread,
          include_commission: includeCommission,
        })
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Request failed')
      }

      const data = await res.json()
      // Initially, result will just have id and status: 'pending'
      setResult(data as LabResult)
    } catch (e: any) {
      setError(e.message || 'An error occurred.')
      setLoading(false)
    }
  }

  const handleChat = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!chatInput.trim() || !result?.id || chatLoading) return

    setChatLoading(true)
    const userMsg = chatInput
    setChatInput('')

    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch(`${API_BASE}/historical-lab/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          backtest_id: result.id,
          message: userMsg
        })
      })

      if (!res.ok) throw new Error('Chat failed')
      const data: LabResult = await res.json()
      setResult(data)
    } catch (e: any) {
      setError(e.message || 'Chat error.')
    } finally {
      setChatLoading(false)
    }
  }

  const metrics = result?.metrics
  const analysis = result?.analysis
  const isProcessing = result?.status === 'pending' || result?.status === 'running'

  return (
    <div className="p-6 space-y-6 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex flex-wrap gap-4 justify-between items-end">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <FlaskConical className="w-6 h-6 text-primary" />
            <h1 className="text-3xl font-bold font-heading">Historical Lab</h1>
          </div>
          <p className="text-muted-foreground text-sm">Professional backtesting & analysis engine running on high-speed Parquet data</p>
        </div>

        {/* Mode Switcher */}
        <div className="bg-muted p-1 rounded-xl flex gap-1 border border-border">
          {(['backtest', 'analysis'] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition-all ${
                mode === m ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {m === 'backtest' ? '📈 Backtest' : '🔬 Deep Analysis'}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6">
        {/* Configuration Desk */}
        <Card className="col-span-12 lg:col-span-4 border-primary/10 bg-card/50">
          <CardHeader className="border-b border-border/50 pb-4">
            <CardTitle className="flex items-center gap-2 text-base">
              <Settings2 className="w-4 h-4 text-primary" /> Configuration Desk
            </CardTitle>
          </CardHeader>
          <CardContent className="p-5 space-y-5">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Symbol</Label>
                <Select value={symbol} onValueChange={setSymbol} disabled={loading}>
                  <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {SYMBOLS.map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Timeframe</Label>
                <Select value={timeframe} onValueChange={setTimeframe} disabled={loading}>
                  <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {TIMEFRAMES.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Start Date</Label>
                <Input type="date" className="h-9" value={startDate} onChange={e => setStartDate(e.target.value)} disabled={loading} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">End Date</Label>
                <Input type="date" className="h-9" value={endDate} onChange={e => setEndDate(e.target.value)} disabled={loading} />
              </div>
            </div>

            {mode === 'backtest' && (
              <div className="space-y-4 animate-in slide-in-from-top-2 duration-200">
                <div className="h-px bg-border/50" />
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Initial Capital ($)</Label>
                    <Input type="number" className="h-9" value={capital} onChange={e => setCapital(e.target.value)} disabled={loading} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Leverage</Label>
                    <Select value={leverage} onValueChange={setLeverage} disabled={loading}>
                      <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {LEVERAGES.map(l => <SelectItem key={l} value={l}>1:{l}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={() => setIncludeSpread(!includeSpread)}
                    disabled={loading}
                    className={`flex-1 py-2 rounded-lg text-xs font-medium border transition-all ${
                      includeSpread ? 'bg-primary/10 border-primary text-primary' : 'border-border text-muted-foreground'
                    }`}
                  >
                    {includeSpread ? '✓' : '+'} Spread
                  </button>
                  <button
                    onClick={() => setIncludeCommission(!includeCommission)}
                    disabled={loading}
                    className={`flex-1 py-2 rounded-lg text-xs font-medium border transition-all ${
                      includeCommission ? 'bg-primary/10 border-primary text-primary' : 'border-border text-muted-foreground'
                    }`}
                  >
                    {includeCommission ? '✓' : '+'} Comm.
                  </button>
                </div>
              </div>
            )}

            <div className="space-y-1.5">
              <Label className="text-xs flex items-center gap-1.5">
                <BrainCircuit className="w-3.5 h-3.5 text-purple-400" />
                Strategy Prompt
              </Label>
              <textarea
                className="w-full h-28 rounded-lg bg-background border border-input p-3 text-sm focus:ring-1 focus:ring-primary outline-none transition-all resize-none"
                placeholder="Describe your strategy here..."
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                disabled={loading}
              />
            </div>

            {error && <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-xs text-destructive">⚠️ {error}</div>}

            <Button className="w-full h-11" onClick={handleRun} disabled={loading}>
              {loading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Processing...</> : <><Play className="mr-2 h-4 w-4 fill-current" /> Run Lab</>}
            </Button>
          </CardContent>
        </Card>

        {/* Results Cockpit */}
        <div className="col-span-12 lg:col-span-8 space-y-5">
          {/* Progress Overlay */}
          {isProcessing && (
            <div className="bg-card/80 backdrop-blur-sm border border-primary/20 rounded-xl p-8 flex flex-col items-center justify-center space-y-4 animate-pulse">
              <div className="w-16 h-16 rounded-full border-4 border-primary/20 border-t-primary animate-spin" />
              <div className="text-center">
                <h3 className="text-lg font-bold">Executing {result?.mode}</h3>
                <p className="text-sm text-muted-foreground">Current Status: <span className="text-primary capitalize">{result?.status}</span></p>
                <p className="text-xs text-muted-foreground mt-2 italic">Vectorizing data and computing strategy math...</p>
              </div>
            </div>
          )}

          {/* Metrics */}
          {mode === 'backtest' && !isProcessing && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <MetricCard label="Sharpe Ratio" value={metrics ? metrics.sharpe_ratio.toFixed(2) : '—'} icon={TrendingUp} color="text-green-400" />
              <MetricCard label="Win Rate" value={metrics ? `${metrics.win_rate_pct.toFixed(1)}%` : '—'} icon={Zap} color="text-yellow-400" />
              <MetricCard label="Profit Factor" value={metrics ? metrics.profit_factor.toFixed(2) : '—'} icon={BarChartHorizontal} color="text-blue-400" />
              <MetricCard label="Max Drawdown" value={metrics ? `${metrics.max_drawdown_pct.toFixed(1)}%` : '—'} icon={AlertTriangle} color="text-red-400" />
            </div>
          )}

          {/* Equity Curve */}
          {mode === 'backtest' && !isProcessing && (
            <Card className="bg-card/50 border-border/50 h-[350px]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2"><HistoryIcon className="w-4 h-4" /> Equity Performance</CardTitle>
              </CardHeader>
              <CardContent className="h-[280px] p-0 pr-4 pb-4">
                <ResponsiveContainer width="100%" height="100%">
                  {result?.equity_curve ? (
                    <AreaChart data={result.equity_curve}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                      <XAxis dataKey="time" fontSize={10} hide />
                      <YAxis fontSize={10} tickLine={false} axisLine={false} tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
                      <Tooltip />
                      <Area type="monotone" dataKey="balance" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.1} />
                    </AreaChart>
                  ) : <div className="h-full flex items-center justify-center text-muted-foreground text-xs italic">Awaiting results...</div>}
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Deep Analysis Charts */}
          {mode === 'analysis' && analysis && !isProcessing && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card className="bg-card/50 border-border/50 h-[250px]">
                <CardHeader className="pb-2"><CardTitle className="text-xs">Hourly Volatility</CardTitle></CardHeader>
                <CardContent className="h-[180px] p-0 pr-4 pb-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={analysis.hourly_volatility}>
                      <XAxis dataKey="hour_utc" fontSize={10} />
                      <YAxis fontSize={10} />
                      <Bar dataKey="avg_range" fill="hsl(var(--primary))" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
              <Card className="bg-card/50 border-border/50 h-[250px]">
                <CardHeader className="pb-2"><CardTitle className="text-xs">Day-of-Week Volatility</CardTitle></CardHeader>
                <CardContent className="h-[180px] p-0 pr-4 pb-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={analysis.day_of_week_volatility}>
                      <XAxis dataKey="day" fontSize={10} />
                      <YAxis fontSize={10} />
                      <Bar dataKey="avg_range" fill="hsl(var(--primary))" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </div>
          )}

          {/* AI Chat Terminal */}
          <Card className="bg-primary/5 border-primary/20 h-[500px] flex flex-col">
            <CardHeader className="pb-3 shrink-0">
              <CardTitle className="text-base flex items-center gap-2"><BrainCircuit className="w-5 h-5 text-primary" /> Quant Research Vault</CardTitle>
            </CardHeader>
            <CardContent className="flex-1 overflow-y-auto space-y-4 p-4">
              {result?.chat_history.map((msg, i) => (
                <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${msg.role === 'user' ? 'bg-primary/20 text-primary' : 'bg-muted'}`}>
                    {msg.role === 'user' ? <UserIcon size={16} /> : <Bot size={16} />}
                  </div>
                  <div className={`p-3 rounded-2xl text-sm max-w-[85%] ${msg.role === 'user' ? 'bg-primary text-primary-foreground rounded-tr-none' : 'bg-muted/50 border border-border/50 rounded-tl-none whitespace-pre-wrap'}`}>
                    {msg.content}
                  </div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </CardContent>
            <div className="p-4 border-t border-border/50 bg-background/50">
              <form onSubmit={handleChat} className="flex gap-2">
                <Input placeholder="Ask a follow-up..." value={chatInput} onChange={e => setChatInput(e.target.value)} disabled={isProcessing || !result || chatLoading} />
                <Button size="icon" type="submit" disabled={isProcessing || !result || chatLoading}><Send size={16} /></Button>
              </form>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
