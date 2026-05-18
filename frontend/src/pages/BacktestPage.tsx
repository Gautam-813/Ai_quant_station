import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import axios from 'axios'

interface Prompt {
  id: string
  text: string
  is_custom: boolean
}

interface BacktestResults {
  metrics: {
    total_return: number
    win_rate: number
    max_drawdown: number
    trades: number
  }
  equity_curve: number[]
  generated_code: string
}

export default function BacktestPage() {
  const [prompts, setPrompts] = useState<Prompt[]>([])
  const [selectedPromptId, setSelectedPromptId] = useState('')
  const [symbol, setSymbol] = useState('XAUUSD')
  const [timeframe, setTimeframe] = useState('15T')
  const [startDate, setStartDate] = useState('2024-01-01')
  const [endDate, setEndDate] = useState('2024-12-31')
  
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<BacktestResults | null>(null)
  const [error, setError] = useState<string | null>(null)
  
  // Model Selection
  const [provider, setProvider] = useState('nvidia')
  const [model, setModel] = useState('qwen/qwen3.5-122b-a10b')
  const [availableProviders, setAvailableProviders] = useState<any[]>([])

  // Fetch providers
  useEffect(() => {
    const fetchProviders = async () => {
      try {
        const res = await axios.get('/api/ai/providers')
        setAvailableProviders(res.data.providers || [])
      } catch (e) { console.error("Providers error", e) }
    }
    fetchProviders()
  }, [])

  // Auto-select first model when provider changes
  useEffect(() => {
    const selectedProv = availableProviders.find(p => p.id === provider)
    if (selectedProv && selectedProv.models.length > 0) {
      if (!selectedProv.models.includes(model)) {
        setModel(selectedProv.models[0])
      }
    }
  }, [provider, availableProviders])

  useEffect(() => {
    fetchPrompts()
  }, [])

  const fetchPrompts = async () => {
    try {
      const res = await axios.get('/api/autopilot/prompts')
      const all = [...res.data.default_prompts, ...res.data.personal_prompts]
      setPrompts(all)
      if (all.length > 0) setSelectedPromptId(all[0].id)
    } catch (err) {
      console.error('Failed to fetch prompts', err)
    }
  }

  const handleRunBacktest = async () => {
    setLoading(true)
    setError(null)
    setResults(null)
    try {
      const res = await axios.post('/api/backtest/run', {
        prompt_id: selectedPromptId,
        symbol,
        timeframe,
        start_date: startDate,
        end_date: endDate,
        provider,
        model
      })
      if (res.data.success) {
        setResults(res.data)
      } else {
        setError(res.data.error || 'Backtest failed')
        if (res.data.generated_code) {
          setResults({ ...res.data, metrics: null, equity_curve: null })
        }
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message)
    } finally {
      setLoading(false)
    }
  }

  const chartData = results?.equity_curve?.map((val, idx) => ({
    name: idx,
    value: val
  })) || []

  return (
    <div className="p-8">
      <h1 className="font-heading text-3xl font-bold mb-8">Prompt Backtesting</h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Configuration */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Configuration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="text-sm font-medium">Select Strategy</label>
              <Select value={selectedPromptId} onValueChange={setSelectedPromptId}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-[300px]">
                  {prompts.map(p => (
                    <SelectItem key={p.id} value={p.id}>
                      <span className={p.is_custom ? "text-purple-400" : "text-blue-400"}>
                        {p.is_custom ? "[Personal]" : `[#${p.id}]`}
                      </span> {p.text.slice(0, 50)}...
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="text-sm font-medium">Symbol</label>
              <Select value={symbol} onValueChange={setSymbol}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="XAUUSD">Gold (XAUUSD)</SelectItem>
                  <SelectItem value="XAGUSD">Silver (XAGUSD)</SelectItem>
                  <SelectItem value="US30">Dow Jones (US30)</SelectItem>
                  <SelectItem value="USOIL">Crude Oil (USOIL)</SelectItem>
                  <SelectItem value="EURUSD">EURUSD</SelectItem>
                  <SelectItem value="GBPUSD">GBPUSD</SelectItem>
                  <SelectItem value="USDJPY">USDJPY</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="text-sm font-medium">Timeframe</label>
              <Select value={timeframe} onValueChange={setTimeframe}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="5T">5 Minutes</SelectItem>
                  <SelectItem value="15T">15 Minutes</SelectItem>
                  <SelectItem value="30T">30 Minutes</SelectItem>
                  <SelectItem value="1H">1 Hour</SelectItem>
                  <SelectItem value="4H">4 Hours</SelectItem>
                  <SelectItem value="1D">1 Day</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium">Start Date</label>
                <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </div>
              <div>
                <label className="text-sm font-medium">End Date</label>
                <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
              </div>
            </div>

            <div className="pt-4 border-t border-border">
              <label className="text-sm font-medium block mb-2 text-primary">Model Selection</label>
              <div className="space-y-3">
                <Select value={provider} onValueChange={setProvider}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select Provider" />
                  </SelectTrigger>
                  <SelectContent>
                    {availableProviders.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Select value={model} onValueChange={setModel}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select Model" />
                  </SelectTrigger>
                  <SelectContent>
                    {availableProviders.find(p => p.id === provider)?.models.map((m: any) => (
                      <SelectItem key={m} value={m}>{m}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Button 
              className="w-full mt-4" 
              onClick={handleRunBacktest} 
              disabled={loading}
            >
              {loading ? "Simulating..." : "Run Vectorized Backtest"}
            </Button>

            {error && (
              <div className="p-3 bg-red-500/10 border border-red-500/30 text-red-400 text-xs rounded">
                {error}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Results */}
        <div className="lg:col-span-2 space-y-8">
          {results?.metrics && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Card>
                <CardContent className="pt-6">
                  <div className="text-sm text-muted-foreground">Total Return</div>
                  <div className={`text-2xl font-bold ${results.metrics.total_return >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    {results.metrics.total_return}%
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <div className="text-sm text-muted-foreground">Win Rate</div>
                  <div className="text-2xl font-bold">{results.metrics.win_rate}%</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <div className="text-sm text-muted-foreground">Max Drawdown</div>
                  <div className="text-2xl font-bold text-red-400">{results.metrics.max_drawdown}%</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <div className="text-sm text-muted-foreground">Trades</div>
                  <div className="text-2xl font-bold">{results.metrics.trades}</div>
                </CardContent>
              </Card>
            </div>
          )}

          {results?.equity_curve && (
            <Card>
              <CardHeader>
                <CardTitle>Equity Curve (Simulated)</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-[300px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                      <XAxis dataKey="name" hide />
                      <YAxis domain={['auto', 'auto']} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '8px' }}
                        itemStyle={{ color: '#22c55e' }}
                        labelStyle={{ display: 'none' }}
                      />
                      <Line 
                        type="monotone" 
                        dataKey="value" 
                        stroke="#22c55e" 
                        strokeWidth={2} 
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          )}

          {results?.generated_code && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">AI Generated Strategy Logic</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="bg-muted p-4 rounded-lg text-xs font-mono overflow-x-auto text-blue-300">
                  {results.generated_code}
                </pre>
              </CardContent>
            </Card>
          )}

          {!results && !loading && (
            <div className="flex flex-col items-center justify-center py-20 text-muted-foreground bg-muted/20 rounded-xl border border-dashed border-border">
              <span className="text-4xl mb-4">🧪</span>
              <p>Configure your strategy and run a simulation to see results.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
