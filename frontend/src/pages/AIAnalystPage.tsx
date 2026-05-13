import { useState, useEffect, useRef } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import axios from 'axios'
import { createChart, CandlestickSeries, CandlestickData, Time } from 'lightweight-charts'
import { DataPreviewTable } from '@/components/ui/data-preview-table'
import { MiniChart } from '@/components/ui/mini-chart'



interface Message {
  role: 'user' | 'assistant'
  content: string
  detected_setup?: any
  detected_action?: any
  data_preview?: string
  detected_chart?: any
  execution_output?: string
  execution_charts?: Array<{title: string, data: number[], color: string, type: string}>
  execution_tables?: Array<{title: string, columns?: string[], rows: any[][]}>
}




interface SymbolOption {
  symbol: string
  type?: string
  name?: string
}

interface LoadedDataInfo {
  source: string
  symbol: string
  startDate: string
  endDate: string
  candles: number
}

interface CandleData {
  time: number
  open: number
  high: number
  low: number
  close: number
}

export default function AIAnalystPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [provider, setProvider] = useState('nvidia')
  const [model, setModel] = useState('qwen/qwen3.5-122b-a10b')
  const [loading, setLoading] = useState(false)
  const [feedbackSent, setFeedbackSent] = useState<Set<number>>(new Set())
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<any>(null)
  const seriesRef = useRef<any>(null)

  const [candleData, setCandleData] = useState<CandleData[]>([])
  
  const [symbol, setSymbol] = useState<string | undefined>(undefined)
  const [customSymbol, setCustomSymbol] = useState('')
  const [loadData, setLoadData] = useState<'yahoo' | 'mt5' | 'none'>('none')
  const [dataPeriod, setDataPeriod] = useState('1mo')
  const [availableSymbols, setAvailableSymbols] = useState<SymbolOption[]>([])
  const [symbolsLoading, setSymbolsLoading] = useState(false)
  
  const [loadedData, setLoadedData] = useState<LoadedDataInfo | null>(null)
  const [dataLoading, setDataLoading] = useState(false)
  const [liveMode, setLiveMode] = useState(false)
  const [timeframe, setTimeframe] = useState('1h')

  useEffect(() => {
    let interval: any
    if (liveMode && loadData !== 'none' && getSymbolValue()) {
      interval = setInterval(() => {
        handleLoadData()
      }, 60000)
    }
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [liveMode, loadData, symbol, customSymbol])

  useEffect(() => {
    if (!chartContainerRef.current) return

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { color: '#1a1a1a' },
        textColor: '#d1d5db'
      },
      grid: {
        vertLines: { color: '#2a2a2a' },
        horzLines: { color: '#2a2a2a' }
      },
      crosshair: {
        mode: 1,
        vertLine: {
          color: '#6b7280',
          labelBackgroundColor: '#374151',
          width: 1,
          style: 2
        },
        horzLine: {
          color: '#6b7280',
          labelBackgroundColor: '#374151',
          width: 1,
          style: 2
        }
      },
      rightPriceScale: {
        borderColor: '#374151'
      },
      timeScale: {
        borderColor: '#374151',
        timeVisible: true,
        secondsVisible: false
      }
    })

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444'
    })

    chartRef.current = chart
    seriesRef.current = candlestickSeries

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ 
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight 
        })
      }
    }

    handleResize()
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [])

  useEffect(() => {
    if (seriesRef.current && candleData.length > 0) {
      const validData = candleData.filter(d => {
        const timeVal = Number(d.time)
        const openVal = Number(d.open)
        const highVal = Number(d.high)
        const lowVal = Number(d.low)
        const closeVal = Number(d.close)
        
        return (
          timeVal > 0 &&
          openVal > 0 &&
          highVal > 0 &&
          lowVal > 0 &&
          closeVal > 0 &&
          !isNaN(timeVal) &&
          !isNaN(openVal) &&
          !isNaN(highVal) &&
          !isNaN(lowVal) &&
          !isNaN(closeVal)
        )
      })

      const formattedData: CandlestickData<Time>[] = validData.map(d => ({
        time: Number(d.time) as Time,
        open: Number(d.open),
        high: Number(d.high),
        low: Number(d.low),
        close: Number(d.close)
      }))
      
      if (formattedData.length > 0) {
        seriesRef.current.setData(formattedData)
        chartRef.current?.timeScale().fitContent()
      }
    }
  }, [candleData])

  const getSymbolValue = () => {
    if (symbol === 'custom' && customSymbol.trim()) {
      return customSymbol.trim().toUpperCase()
    }
    if (symbol === undefined || symbol === '' || symbol === 'none') {
      return ''
    }
    return symbol
  }

  const handleLoadData = async () => {
    if (loadData === 'none' || !getSymbolValue()) {
      return
    }

    setDataLoading(true)
    try {
      let data: CandleData[] = []

      if (loadData === 'yahoo') {
        const res = await axios.get(`/api/data/yahoo/${getSymbolValue()}?period=${dataPeriod}`)
        if (res.data.success && res.data.data?.length > 0) {
          data = res.data.data.map((d: any) => ({
            time: typeof d.time === 'number' ? d.time : Math.floor(new Date(d.time).getTime() / 1000),
            open: d.open,
            high: d.high,
            low: d.low,
            close: d.close
          }))
          const startDate = data[0].time
          const endDate = data[data.length - 1].time
          setLoadedData({
            source: loadData,
            symbol: getSymbolValue(),
            startDate: new Date(startDate * 1000).toLocaleDateString(),
            endDate: new Date(endDate * 1000).toLocaleDateString(),
            candles: data.length
          })
        }
      } else if (loadData === 'mt5') {
        const res = await axios.post('/api/mt5/data/latest', {
          symbol: getSymbolValue(),
          timeframe: timeframe,
          count: 1000
        })
        if (res.data.success && res.data.data?.length > 0) {
          data = res.data.data.map((d: any) => ({
            time: typeof d.time === 'number' ? d.time : Math.floor(new Date(d.time).getTime() / 1000),
            open: d.open,
            high: d.high,
            low: d.low,
            close: d.close
          }))
          const startDate = data[0].time
          const endDate = data[data.length - 1].time
          setLoadedData({
            source: loadData,
            symbol: getSymbolValue(),
            startDate: new Date(startDate * 1000).toLocaleDateString(),
            endDate: new Date(endDate * 1000).toLocaleDateString(),
            candles: data.length
          })
        }
      }

      setCandleData(data)
    } catch (error) {
      console.error('Failed to load data:', error)
      setLoadedData(null)
      setCandleData([])
    } finally {
      setDataLoading(false)
    }
  }

  useEffect(() => {
    const fetchSymbols = async () => {
      if (loadData === 'none') {
        setAvailableSymbols([])
        return
      }

      setSymbolsLoading(true)
      try {
        if (loadData === 'yahoo') {
          const res = await axios.get('/api/data/yahoo/symbols')
          setAvailableSymbols(res.data.symbols || [])
        } else if (loadData === 'mt5') {
          const res = await axios.get('/api/mt5/symbols')
          if (res.data.success) {
            setAvailableSymbols(res.data.symbols || [])
          } else {
            setAvailableSymbols([])
          }
        }
      } catch (error) {
        console.error('Failed to fetch symbols:', error)
        setAvailableSymbols([])
      } finally {
        setSymbolsLoading(false)
      }
    }

    fetchSymbols()
  }, [loadData])

  const handleSend = async () => {
    if (!input.trim()) return

    const userMessage: Message = { role: 'user', content: input }
    setMessages(prev => [...prev, userMessage])
    setInput('')
    setLoading(true)

    try {
      const allMessages = [...messages, userMessage].map(m => ({
        role: m.role,
        content: m.content
      }))

      const res = await axios.post('/api/ai/chat', {
        messages: allMessages,
        provider,
        model,
        symbol: loadData !== 'none' ? getSymbolValue() : null,
        load_market_data: loadData !== 'none' ? loadData : null,
        data_period: dataPeriod,
        candle_count: 1000,
        timeframe: timeframe,
        // Send loaded candle data directly to AI
        candle_data: candleData.length > 0 ? candleData : null
      })

      const assistantMessage: Message = {
        role: 'assistant',
        content: res.data.message,
        detected_setup: res.data.detected_setup,
        detected_action: res.data.detected_action,
        data_preview: res.data.data_preview,
        detected_chart: res.data.detected_chart,
        execution_output: res.data.execution_output,
        execution_charts: res.data.execution_charts,
        execution_tables: res.data.execution_tables
      }




      setMessages(prev => [...prev, assistantMessage])
    } catch (error: any) {
      console.error('Chat error:', error)
      const errorMsg = error.response?.data?.detail || error.message || 'An error occurred'
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: `Error: ${errorMsg}` 
      }])
    } finally {
      setLoading(false)
    }
  }

  const handleFeedback = async (idx: number, isHelpful: boolean) => {
    if (feedbackSent.has(idx)) return
    try {
      await axios.post('/api/analytics/feedback', {
        is_helpful: isHelpful
      })
      setFeedbackSent(prev => new Set([...prev, idx]))
    } catch (error) {
      console.error('Feedback submission failed:', error)
    }
  }

  const handleTradeExecute = async (setup: any) => {
    try {
      await axios.post('/api/trade/order', {
        symbol: setup.symbol,
        action: setup.direction,
        volume: setup.lot_size,
        entry_price: setup.order_type === 'market' ? null : setup.entry_price,
        sl: setup.stop_loss,
        tp: setup.take_profit
      })
    } catch (error) {
      console.error('Trade execution failed:', error)
    }
  }

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <div className="p-4 pb-2">
        <h1 className="font-heading text-2xl font-bold">AI Analyst</h1>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-4">
        <Card className="w-full">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-4 flex-wrap">
              <div>
                <Select value={provider} onValueChange={setProvider}>
                  <SelectTrigger className="w-32">
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
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger className="w-52">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="qwen/qwen3.5-122b-a10b">Qwen 3.5 122B</SelectItem>
                  <SelectItem value="deepseek-ai/deepseek-v3.1">DeepSeek V3.1</SelectItem>
                  <SelectItem value="llama3-70b-8192">Llama 3 70B</SelectItem>
                  <SelectItem value="gemini-2.5-flash">Gemini Flash</SelectItem>
                </SelectContent>
              </Select>
              
              <div className="flex items-center gap-2 border-l pl-4">
                <span className="text-sm text-muted-foreground">Data:</span>
                <Select value={loadData} onValueChange={(v: 'yahoo' | 'mt5' | 'none') => setLoadData(v)}>
                  <SelectTrigger className="w-24">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    <SelectItem value="yahoo">Yahoo</SelectItem>
                    <SelectItem value="mt5">MT5</SelectItem>
                  </SelectContent>
                </Select>
                
                {loadData !== 'none' && (
                  <>
                    <Select 
                      value={symbol || ''} 
                      onValueChange={(val) => setSymbol(val)}
                    >
                      <SelectTrigger className="w-32 h-8" disabled={symbolsLoading}>
                        <SelectValue placeholder={symbolsLoading ? "Loading..." : "Symbol"} />
                      </SelectTrigger>
                      <SelectContent>
                        {availableSymbols.length > 0 ? (
                          <>
                            <SelectItem value="custom">Custom...</SelectItem>
                            {availableSymbols.slice(0, 30).map((sym) => (
                              <SelectItem key={sym.symbol} value={sym.symbol}>
                                {sym.name || sym.symbol}
                              </SelectItem>
                            ))}
                          </>
                        ) : (
                          <div className="p-2 text-sm text-muted-foreground">No symbols</div>
                        )}
                      </SelectContent>
                    </Select>
                    {symbol === 'custom' && (
                      <Input
                        placeholder="Symbol"
                        value={customSymbol}
                        onChange={(e) => setCustomSymbol(e.target.value.toUpperCase())}
                        className="w-20 h-8"
                      />
                    )}
                    <Select value={dataPeriod} onValueChange={setDataPeriod}>
                      <SelectTrigger className="w-20 h-8">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="1d">1D</SelectItem>
                        <SelectItem value="1w">1W</SelectItem>
                        <SelectItem value="1mo">1M</SelectItem>
                        <SelectItem value="3mo">3M</SelectItem>
                      </SelectContent>
                    </Select>
                    
                    <Select value={timeframe} onValueChange={setTimeframe}>
                      <SelectTrigger className="w-16 h-8">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="1m">1m</SelectItem>
                        <SelectItem value="5m">5m</SelectItem>
                        <SelectItem value="15m">15m</SelectItem>
                        <SelectItem value="30m">30m</SelectItem>
                        <SelectItem value="1h">1h</SelectItem>
                        <SelectItem value="4h">4h</SelectItem>
                        <SelectItem value="1d">1d</SelectItem>
                      </SelectContent>
                    </Select>

                    <Button 
                      size="sm" 
                      variant="outline"
                      onClick={handleLoadData}
                      disabled={!getSymbolValue() || dataLoading}
                    >
                      {dataLoading ? 'Loading...' : 'Load'}
                    </Button>
                    
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={liveMode}
                        onChange={(e) => setLiveMode(e.target.checked)}
                        className="w-4 h-4 rounded"
                      />
                      <span className="text-xs">Live</span>
                    </label>
                  </>
                )}
              </div>
            </div>

            {loadedData && (
              <div className="flex items-center gap-3 mt-2 text-sm text-green-400 bg-green-500/10 rounded px-3 py-1.5 w-fit">
                <span>{loadedData.symbol}</span>
                <span className="text-muted-foreground">|</span>
                <span>{loadedData.startDate} → {loadedData.endDate}</span>
                <span className="text-muted-foreground">|</span>
                <span>{loadedData.candles} candles</span>
                <Button 
                  size="sm" 
                  variant="ghost" 
                  className="h-6 w-6 p-0 ml-1"
                  onClick={() => { setLoadedData(null); setCandleData([]) }}
                >
                  ✕
                </Button>
              </div>
            )}
          </CardHeader>
        </Card>

        <Card className="w-full min-h-[350px]">
          <CardContent className="p-0">
            <div 
              ref={chartContainerRef} 
              className="w-full h-[350px]"
            />
          </CardContent>
        </Card>

        <div className="space-y-3">
          {messages.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">
              Ask the AI analyst about a symbol...
            </p>
          ) : (
            messages.map((msg, idx) => (
              <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] p-4 rounded-lg ${msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'}`}>
                  <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
                  
                  {msg.detected_setup && (
                    <div className="mt-3 p-3 bg-background rounded border border-green-500/30">
                      <p className="font-bold text-green-500 text-sm mb-2">🎯 Trade Setup</p>
                      <p className="text-sm">{msg.detected_setup.direction} {msg.detected_setup.symbol}</p>
                      <p className="text-xs text-muted-foreground">
                        Entry: {msg.detected_setup.entry_price} | SL: {msg.detected_setup.stop_loss} | TP: {msg.detected_setup.take_profit}
                      </p>
                      <Button size="sm" className="mt-2" onClick={() => handleTradeExecute(msg.detected_setup)}>
                        Execute Trade
                      </Button>
                    </div>
                  )}

                  {msg.data_preview && (
                    <DataPreviewTable data={msg.data_preview} />
                  )}

                  {msg.detected_chart && (
                    <MiniChart
                      title={msg.detected_chart.title}
                      data={msg.detected_chart.data}
                      color={msg.detected_chart.color}
                    />
                  )}

                  {msg.execution_charts && msg.execution_charts.length > 0 && (
                    <div className="mt-3 space-y-3">
                      {msg.execution_charts.map((chart, idx) => (
                        <MiniChart
                          key={`exec-chart-${idx}`}
                          title={chart.title}
                          data={chart.data}
                          color={chart.color || '#2563eb'}
                        />
                      ))}
                    </div>
                  )}

                  {msg.execution_tables && msg.execution_tables.length > 0 && (
                    <div className="mt-3 space-y-3">
                      {msg.execution_tables.map((table, idx) => (
                        <Card key={`exec-table-${idx}`} className="bg-background/50 border-muted">
                          <CardHeader className="py-2 px-3">
                            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                              {table.title}
                            </CardTitle>
                          </CardHeader>
                          <CardContent className="p-0">
                            <div className="overflow-x-auto">
                              <table className="w-full text-xs border-collapse">
                                {table.columns && table.columns.length > 0 && (
                                  <thead>
                                    <tr>
                                      {table.columns.map((col, colIdx) => (
                                        <th
                                          key={colIdx}
                                          className="border border-border/50 bg-muted px-2 py-1 text-left font-medium text-foreground"
                                        >
                                          {col}
                                        </th>
                                      ))}
                                    </tr>
                                  </thead>
                                )}
                                <tbody>
                                  {table.rows.map((row, rowIdx) => (
                                    <tr key={rowIdx} className="border-b border-border/30">
                                      {row.map((cell, cellIdx) => (
                                        <td
                                          key={cellIdx}
                                          className="border border-border/30 px-2 py-1 text-foreground"
                                        >
                                          {cell !== null && cell !== undefined ? String(cell) : ''}
                                        </td>
                                      ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  )}

                  {msg.execution_output && (
                    <div className="mt-3 p-3 bg-zinc-950 rounded border border-zinc-800 font-mono text-xs">
                      <p className="text-zinc-500 mb-1 border-b border-zinc-800 pb-1">Execution Output:</p>
                      <pre className="text-zinc-300 overflow-x-auto whitespace-pre-wrap">{msg.execution_output}</pre>
                    </div>
                  )}



                  
                  {msg.role === 'assistant' && (
                    <div className="mt-2 pt-2 border-t border-border/30 flex justify-end gap-2">
                      {feedbackSent.has(idx) ? (
                        <span className="text-xs text-muted-foreground">Thanks!</span>
                      ) : (
                        <>
                          <button onClick={() => handleFeedback(idx, true)} className="text-xs text-muted-foreground hover:text-green-500 transition-colors" title="Helpful">👍</button>
                          <button onClick={() => handleFeedback(idx, false)} className="text-xs text-muted-foreground hover:text-red-500 transition-colors" title="Not helpful">👎</button>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>

        <div className="flex gap-2 sticky bottom-0 bg-background py-2">
          <Input
            placeholder="Ask about a symbol..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            disabled={loading}
            className="flex-1"
          />
          <Button onClick={handleSend} disabled={loading}>
            {loading ? '...' : 'Send'}
          </Button>
        </div>
      </div>
    </div>
  )
}