import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import axios from 'axios'

interface SymbolInfo {
  name: string; ask: number; bid: number
}
interface Position {
  ticket: number; symbol: string; direction: string; volume: number
  entry_price: number; current_price: number; sl: number | null
  tp: number | null; profit: number
}

export default function TerminalPage() {
  const { toast } = useToast()
  const [symbols, setSymbols] = useState<SymbolInfo[]>([])
  const [selectedSymbol, setSelectedSymbol] = useState('XAUUSD')
  const [orderType, setOrderType] = useState('market')
  const [direction, setDirection] = useState('BUY')
  const [volume, setVolume] = useState(0.1)
  const [price, setPrice] = useState('')
  const [sl, setSl] = useState('')
  const [tp, setTp] = useState('')
  const [positions, setPositions] = useState<Position[]>([])
  const [loading, setLoading] = useState(true)
  const [orderLoading, setOrderLoading] = useState(false)

  useEffect(() => { fetchSymbols(); fetchPositions() }, [])

  const fetchSymbols = async () => {
    try { setSymbols((await axios.get('/api/mt5/symbols/all')).data.symbols || []) }
    catch { console.error('Failed to fetch symbols') }
  }

  const fetchPositions = async () => {
    try { setPositions((await axios.get('/api/mt5/positions')).data.positions || []) }
    catch { console.error('Failed to fetch positions') }
    finally { setLoading(false) }
  }

  const handleOrder = async () => {
    setOrderLoading(true)
    try {
      const action = orderType === 'market' ? direction : `${direction}_${orderType.toUpperCase()}`
      await axios.post('/api/trade/order', {
        symbol: selectedSymbol, action, volume,
        price: price ? parseFloat(price) : null,
        sl: sl ? parseFloat(sl) : null, tp: tp ? parseFloat(tp) : null
      })
      toast({ title: "Order placed", description: `${direction} ${selectedSymbol} x${volume}` })
      fetchPositions(); setPrice(''); setSl(''); setTp('')
    } catch (error: any) {
      toast({ title: "Order failed", description: error.response?.data?.detail || error.message, variant: 'destructive' })
    } finally { setOrderLoading(false) }
  }

  const handleClose = async (ticket: number) => {
    try { await axios.post('/api/trade/close', { ticket }); fetchPositions(); toast({ title: "Position closed" }) }
    catch { toast({ title: "Close failed", variant: 'destructive' }) }
  }

  return (
    <div className="p-3 sm:p-6 md:p-8">
      <h1 className="font-heading text-xl sm:text-2xl md:text-3xl font-bold mb-4 sm:mb-6 md:mb-8">Live Terminal</h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6 lg:gap-8">
        {/* Order Form */}
        <Card className="lg:col-span-1">
          <CardHeader className="px-3 sm:px-4 md:px-6 pt-3 sm:pt-4 md:pt-6 pb-2 sm:pb-3">
            <CardTitle className="text-sm sm:text-base md:text-lg">Place Order</CardTitle>
          </CardHeader>
          <CardContent className="px-3 sm:px-4 md:px-6 pb-3 sm:pb-4 md:pb-6 space-y-3 sm:space-y-4">
            <div>
              <Label className="text-xs sm:text-sm">Symbol</Label>
              <Select value={selectedSymbol} onValueChange={setSelectedSymbol}>
                <SelectTrigger className="text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {symbols.map((sym) => (
                    <SelectItem key={sym.name} value={sym.name} className="text-sm">{sym.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs sm:text-sm">Direction</Label>
              <div className="grid grid-cols-2 gap-2 mt-1">
                <Button size="sm" variant={direction === 'BUY' ? 'default' : 'outline'} onClick={() => setDirection('BUY')} className="text-xs sm:text-sm">BUY</Button>
                <Button size="sm" variant={direction === 'SELL' ? 'default' : 'outline'} onClick={() => setDirection('SELL')} className="text-xs sm:text-sm">SELL</Button>
              </div>
            </div>
            <div>
              <Label className="text-xs sm:text-sm">Order Type</Label>
              <Select value={orderType} onValueChange={setOrderType}>
                <SelectTrigger className="text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="market">Market</SelectItem>
                  <SelectItem value="limit">Limit</SelectItem>
                  <SelectItem value="stop">Stop</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:gap-3">
              <div>
                <Label className="text-xs sm:text-sm">Volume</Label>
                <Input type="number" step="0.01" value={volume} onChange={(e) => { const v = parseFloat(e.target.value); setVolume(isNaN(v) ? 0 : v) }} className="text-sm h-9 sm:h-10" />
              </div>
              {orderType !== 'market' && (
                <div>
                  <Label className="text-xs sm:text-sm">Price</Label>
                  <Input type="number" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} className="text-sm h-9 sm:h-10" />
                </div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2 sm:gap-3">
              <div>
                <Label className="text-xs sm:text-sm">SL</Label>
                <Input type="number" step="0.01" placeholder="SL" value={sl} onChange={(e) => setSl(e.target.value)} className="text-sm h-9 sm:h-10" />
              </div>
              <div>
                <Label className="text-xs sm:text-sm">TP</Label>
                <Input type="number" step="0.01" placeholder="TP" value={tp} onChange={(e) => setTp(e.target.value)} className="text-sm h-9 sm:h-10" />
              </div>
            </div>
            <Button onClick={handleOrder} className="w-full text-sm" disabled={orderLoading}>
              {orderLoading ? 'Placing...' : `Execute ${direction}`}
            </Button>
          </CardContent>
        </Card>

        {/* Open Positions */}
        <Card className="lg:col-span-2">
          <CardHeader className="px-3 sm:px-4 md:px-6 pt-3 sm:pt-4 md:pt-6 pb-2 sm:pb-3">
            <CardTitle className="text-sm sm:text-base md:text-lg">Open Positions ({positions.length})</CardTitle>
          </CardHeader>
          <CardContent className="px-3 sm:px-4 md:px-6 pb-3 sm:pb-4 md:pb-6">
            {loading ? (
              <div className="text-center py-6 sm:py-8 text-muted-foreground text-sm">Loading...</div>
            ) : positions.length === 0 ? (
              <p className="text-muted-foreground text-center py-6 sm:py-8 text-sm">No open positions</p>
            ) : (
              <div className="overflow-x-auto -mx-3 sm:mx-0">
                <table className="w-full text-xs sm:text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-2 px-1 sm:px-2 font-medium text-muted-foreground">Symbol</th>
                      <th className="text-left py-2 px-1 sm:px-2 font-medium text-muted-foreground hidden sm:table-cell">Dir</th>
                      <th className="text-right py-2 px-1 sm:px-2 font-medium text-muted-foreground">Vol</th>
                      <th className="text-right py-2 px-1 sm:px-2 font-medium text-muted-foreground hidden md:table-cell">Entry</th>
                      <th className="text-right py-2 px-1 sm:px-2 font-medium text-muted-foreground hidden md:table-cell">Current</th>
                      <th className="text-right py-2 px-1 sm:px-2 font-medium text-muted-foreground">P&L</th>
                      <th className="text-right py-2 px-1 sm:px-2 font-medium text-muted-foreground">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((pos) => (
                      <tr key={pos.ticket} className="border-b border-border/50 hover:bg-muted/50">
                        <td className="py-2 px-1 sm:px-2 font-medium">{pos.symbol}</td>
                        <td className={`py-2 px-1 sm:px-2 hidden sm:table-cell ${pos.direction === 'BUY' ? 'text-green-500' : 'text-red-500'}`}>{pos.direction}</td>
                        <td className="text-right py-2 px-1 sm:px-2">{pos.volume}</td>
                        <td className="text-right py-2 px-1 sm:px-2 hidden md:table-cell">{pos.entry_price.toFixed(2)}</td>
                        <td className="text-right py-2 px-1 sm:px-2 hidden md:table-cell">{pos.current_price.toFixed(2)}</td>
                        <td className={`text-right py-2 px-1 sm:px-2 ${pos.profit >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                          ${pos.profit.toFixed(2)}
                        </td>
                        <td className="text-right py-2 px-1 sm:px-2">
                          <Button size="sm" variant="destructive" onClick={() => handleClose(pos.ticket)} className="text-xs h-7 sm:h-8 px-2 sm:px-3">
                            Close
                          </Button>
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
    </div>
  )
}
