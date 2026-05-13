import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import axios from 'axios'

interface LogEntry {
  timestamp: string
  level: string
  message: string
}

interface TradeResult {
  id: number
  prompt_number: number
  prompt_text: string
  symbol: string
  direction: string
  entry_price: number | null
  stop_loss: number | null
  take_profit: number | null
  lot_size: number
  mt5_ticket: number | null
  executed_at: string
  result: string | null
  profit: number | null
  closed_at: string | null
  reasoning: string | null
  confidence: number | null
}

interface AutopilotStatus {
  enabled: boolean
  running: boolean
  settings: {
    enabled: boolean
    interval_seconds: number
    default_lot: number
    max_trades_per_day: number
    cooldown_minutes: number
    max_daily_loss: number
    mt5_terminal_path: string | null
    mt5_connector_url: string | null
    symbol: string
    provider: string
    model: string
    mt5_connected: boolean
  } | null
  stats: {
    total_runs: number
    trades_executed: number
    success_count: number
    error_count: number
    last_run: string | null
  }
  logs: LogEntry[]
}

export default function AutopilotPage() {
  const [status, setStatus] = useState<AutopilotStatus | null>(null)
  const [trades, setTrades] = useState<TradeResult[]>([])
  const [loading, setLoading] = useState(true)

  // Settings form
  const [intervalVal, setIntervalVal] = useState('300')
  const [lotSize, setLotSize] = useState('0.10')
  const [symbol, setSymbol] = useState('XAUUSD')
  const [provider, setProvider] = useState('nvidia')
  const [model, setModel] = useState('qwen/qwen3.5-122b-a10b')
  const [terminalPath, setTerminalPath] = useState('')
  const [connectorUrl, setConnectorUrl] = useState('')
  const [mt5Connected, setMt5Connected] = useState(false)

  useEffect(() => {
    fetchStatus()
    fetchTrades()
    const intervalId: ReturnType<typeof setInterval> = setInterval(() => {
      fetchStatus()
    }, 5000)
    return () => clearInterval(intervalId)
  }, [])

  const fetchStatus = async () => {
    try {
      const res = await axios.get('/api/autopilot/status')
      setStatus(res.data)
      if (res.data.settings) {
        setIntervalVal(String(res.data.settings.interval_seconds))
        setLotSize(String(res.data.settings.default_lot))
        setSymbol(res.data.settings.symbol)
        setProvider(res.data.settings.provider)
        setModel(res.data.settings.model)
        setTerminalPath(res.data.settings.mt5_terminal_path || '')
        setConnectorUrl(res.data.settings.mt5_connector_url || '')
        setMt5Connected(res.data.settings.mt5_connected || false)
      }
    } catch (error) {
      console.error('Failed to fetch status:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchTrades = async () => {
    try {
      const res = await axios.get('/api/autopilot/results?limit=50')
      setTrades(res.data)
    } catch (error) {
      console.error('Failed to fetch trades:', error)
    }
  }

  const handleStart = async () => {
    await saveSettings()
    try {
      await axios.post('/api/autopilot/start')
      fetchStatus()
    } catch (error) {
      console.error('Failed to start autopilot:', error)
    }
  }

  const handleStop = async () => {
    try {
      await axios.post('/api/autopilot/stop')
      fetchStatus()
    } catch (error) {
      console.error('Failed to stop autopilot:', error)
    }
  }

  const saveSettings = async () => {
    try {
      await axios.post('/api/autopilot/settings', {
        interval_seconds: parseInt(intervalVal),
        default_lot: parseFloat(lotSize),
        max_trades_per_day: 10,
        cooldown_minutes: 5,
        max_daily_loss: -50,
        mt5_terminal_path: terminalPath,
        mt5_connector_url: connectorUrl || null,
        symbol: symbol,
        provider: provider,
        model: model
      })
    } catch (error) {
      console.error('Failed to save settings:', error)
    }
  }

  const connectMT5 = async () => {
    try {
      const res = await axios.post('/api/autopilot/connect-mt5', null, {
        params: { terminal_path: terminalPath || null }
      })
      if (res.data.success) {
        setMt5Connected(true)
        alert('MT5 Connected Successfully!')
      } else {
        alert('Failed to connect: ' + res.data.message)
      }
      fetchStatus()
    } catch (error: any) {
      alert('Error: ' + (error.response?.data?.detail || error.message))
    }
  }

  const getLogColor = (level: string) => {
    switch (level) {
      case 'SUCCESS': return 'text-green-400'
      case 'ERROR': return 'text-red-400'
      default: return 'text-gray-300'
    }
  }

  const getResultBadge = (result: string | null) => {
    switch (result) {
      case 'TP_HIT': return <span className="px-2 py-1 bg-green-500/20 text-green-400 rounded text-xs">TP HIT</span>
      case 'SL_HIT': return <span className="px-2 py-1 bg-red-500/20 text-red-400 rounded text-xs">SL HIT</span>
      case 'MANUAL_CLOSE': return <span className="px-2 py-1 bg-yellow-500/20 text-yellow-400 rounded text-xs">MANUAL</span>
      case 'PENDING': return <span className="px-2 py-1 bg-blue-500/20 text-blue-400 rounded text-xs">OPEN</span>
      default: return <span className="px-2 py-1 bg-gray-500/20 text-gray-400 rounded text-xs">-</span>
    }
  }

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[400px]">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    )
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="font-heading text-3xl font-bold">Autopilot</h1>
        <div className="flex items-center gap-4">
          <div className={`px-4 py-2 rounded-full ${status?.enabled ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>
            {status?.enabled ? 'Running' : 'Stopped'}
          </div>
          {status?.enabled ? (
            <Button variant="destructive" onClick={handleStop}>Stop</Button>
          ) : (
            <Button onClick={handleStart}>Start Autopilot</Button>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Cycles</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{status?.stats.total_runs || 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Trades Executed</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{status?.stats.trades_executed || 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Success</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-500">{status?.stats.success_count || 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Errors</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-500">{status?.stats.error_count || 0}</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Settings */}
        <Card>
          <CardHeader>
            <CardTitle>Settings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* MT5 Connection */}
            <div className="p-4 bg-muted/30 rounded-lg">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">MT5 Terminal</span>
                  <span className={`px-2 py-1 rounded text-xs ${mt5Connected ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>
                    {mt5Connected ? 'Connected' : 'Disconnected'}
                  </span>
                </div>
                <Button
                  size="sm"
                  variant={mt5Connected ? "outline" : "default"}
                  onClick={connectMT5}
                  disabled={status?.enabled}
                >
                  {mt5Connected ? 'Reconnect' : 'Connect'}
                </Button>
              </div>
              <Input
                placeholder="C:\Program Files\MetaTrader 5\terminal64.exe"
                value={terminalPath}
                onChange={(e) => setTerminalPath(e.target.value)}
                disabled={status?.enabled}
                className="text-xs"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Leave empty for default MT5 terminal
              </p>
              {/* MT5 Connector URL */}
              <label className="text-sm text-muted-foreground mt-3 block">MT5 Connector URL</label>
              <Input
                placeholder="http://192.168.1.100:5001"
                value={connectorUrl}
                onChange={(e) => setConnectorUrl(e.target.value)}
                disabled={status?.enabled}
                className="text-xs"
              />
              <p className="text-xs text-muted-foreground mt-1">
                IP:Port of MT5 Connector service (leave empty for localhost)
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm text-muted-foreground">Cycle Interval</label>
                <Select 
                  value={intervalVal} 
                  onValueChange={setIntervalVal}
                  disabled={status?.enabled}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="60">1 minute</SelectItem>
                    <SelectItem value="180">3 minutes</SelectItem>
                    <SelectItem value="300">5 minutes</SelectItem>
                    <SelectItem value="600">10 minutes</SelectItem>
                    <SelectItem value="900">15 minutes</SelectItem>
                    <SelectItem value="1800">30 minutes</SelectItem>
                    <SelectItem value="3600">1 hour</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-sm text-muted-foreground">Lot Size</label>
                <Input
                  type="number"
                  step="0.01"
                  value={lotSize}
                  onChange={(e) => setLotSize(e.target.value)}
                  disabled={status?.enabled}
                />
              </div>
            </div>

            <div>
              <label className="text-sm text-muted-foreground">Symbol</label>
              <Input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                disabled={status?.enabled}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm text-muted-foreground">AI Provider</label>
                <Select value={provider} onValueChange={setProvider} disabled={status?.enabled}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="nvidia">NVIDIA</SelectItem>
                    <SelectItem value="groq">Groq</SelectItem>
                    <SelectItem value="openrouter">OpenRouter</SelectItem>
                    <SelectItem value="gemini">Gemini</SelectItem>
                    <SelectItem value="cerebras">Cerebras</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-sm text-muted-foreground">Model</label>
                <Select value={model} onValueChange={setModel} disabled={status?.enabled}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="qwen/qwen3.5-122b-a10b">Qwen 3.5 122B</SelectItem>
                    <SelectItem value="deepseek-ai/deepseek-v3.1">DeepSeek V3.1</SelectItem>
                    <SelectItem value="llama3-70b-8192">Llama 3 70B</SelectItem>
                    <SelectItem value="gemini-2.5-flash">Gemini Flash</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Button onClick={saveSettings} variant="outline" className="w-full">
              Save Settings
            </Button>
          </CardContent>
        </Card>

        {/* Logs */}
        <Card>
          <CardHeader>
            <CardTitle>Live Logs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px] overflow-y-auto font-mono text-xs space-y-1">
              {status?.logs && status.logs.length > 0 ? (
                status.logs.map((log, idx) => (
                  <div key={idx} className="flex gap-2">
                    <span className="text-muted-foreground">[{log.timestamp}]</span>
                    <span className={getLogColor(log.level)}>{log.level}</span>
                    <span className="text-gray-300">{log.message}</span>
                  </div>
                ))
              ) : (
                <div className="text-muted-foreground text-center py-8">No logs yet</div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Trade History */}
      <Card className="mt-8">
        <CardHeader>
          <CardTitle>Trade History</CardTitle>
        </CardHeader>
        <CardContent>
          {trades.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">No trades yet</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-3 px-2">Time</th>
                    <th className="text-left py-3 px-2">#</th>
                    <th className="text-left py-3 px-2">Symbol</th>
                    <th className="text-left py-3 px-2">Dir</th>
                    <th className="text-right py-3 px-2">Entry</th>
                    <th className="text-right py-3 px-2">SL</th>
                    <th className="text-right py-3 px-2">TP</th>
                    <th className="text-right py-3 px-2">Lot</th>
                    <th className="text-left py-3 px-2">Ticket</th>
                    <th className="text-left py-3 px-2">Result</th>
                    <th className="text-right py-3 px-2">P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((trade) => (
                    <tr key={trade.id} className="border-b border-border/30 hover:bg-muted/50">
                      <td className="py-3 px-2 text-xs">{trade.executed_at?.slice(11, 19) || '-'}</td>
                      <td className="py-3 px-2 text-xs">{trade.prompt_number}</td>
                      <td className="py-3 px-2 font-medium">{trade.symbol}</td>
                      <td className={`py-3 px-2 ${trade.direction === 'BUY' ? 'text-green-500' : 'text-red-500'}`}>
                        {trade.direction}
                      </td>
                      <td className="py-3 px-2 text-right">{trade.entry_price?.toFixed(2) || '-'}</td>
                      <td className="py-3 px-2 text-right text-red-400">{trade.stop_loss?.toFixed(2) || '-'}</td>
                      <td className="py-3 px-2 text-right text-green-400">{trade.take_profit?.toFixed(2) || '-'}</td>
                      <td className="py-3 px-2 text-right">{trade.lot_size}</td>
                      <td className="py-3 px-2">{trade.mt5_ticket || '-'}</td>
                      <td className="py-3 px-2">{getResultBadge(trade.result)}</td>
                      <td className={`py-3 px-2 text-right font-medium ${trade.profit && trade.profit >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                        {trade.profit !== null ? `$${trade.profit.toFixed(2)}` : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}