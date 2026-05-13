import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import api from '@/lib/api'

interface Symbol {
  name: string
  ask: number
  bid: number
}

interface Position {
  ticket: number
  symbol: string
  direction: string
  volume: number
  entry_price: number
  current_price: number
  sl: number | null
  tp: number | null
  profit: number
}

export default function TerminalPage() {
  const [symbols, setSymbols] = useState<Symbol[]>([])
  const [selectedSymbol, setSelectedSymbol] = useState('XAUUSD')
  const [orderType, setOrderType] = useState('market')
  const [direction, setDirection] = useState('BUY')
  const [volume, setVolume] = useState(0.1)
  const [price, setPrice] = useState('')
  const [sl, setSl] = useState('')
  const [tp, setTp] = useState('')
  const [positions, setPositions] = useState<Position[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchSymbols()
    fetchPositions()
  }, [])

  const fetchSymbols = async () => {
    try {
      const res = await api.get('/mt5/symbols/all')
      setSymbols(res.data.symbols || [])
    } catch (error) {
      console.error('Failed to fetch symbols:', error)
    }
  }

  const fetchPositions = async () => {
    try {
      const res = await api.get('/mt5/positions')
      setPositions(res.data.positions || [])
    } catch (error) {
      console.error('Failed to fetch positions:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleOrder = async () => {
    try {
      const action = orderType === 'market' 
        ? direction 
        : `${direction}_${orderType.toUpperCase()}`
      
      await api.post('/trade/order', {
        symbol: selectedSymbol,
        action,
        volume,
        price: price ? parseFloat(price) : null,
        sl: sl ? parseFloat(sl) : null,
        tp: tp ? parseFloat(tp) : null
      })
      
      // Refresh positions
      fetchPositions()
      
      // Clear form
      setPrice('')
      setSl('')
      setTp('')
    } catch (error: any) {
      console.error('Order failed:', error.response?.data?.detail || error.message)
    }
  }

  const handleClose = async (ticket: number) => {
    try {
      await api.post('/trade/close', { ticket })
      fetchPositions()
    } catch (error) {
      console.error('Close failed:', error)
    }
  }

  return (
    <div className="p-8">
      <h1 className="font-heading text-3xl font-bold mb-8">Live Terminal</h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Order Form */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Place Order</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label>Symbol</Label>
              <Select value={selectedSymbol} onValueChange={setSelectedSymbol}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {symbols.slice(0, 20).map((sym) => (
                    <SelectItem key={sym.name} value={sym.name}>
                      {sym.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Button 
                variant={direction === 'BUY' ? 'default' : 'outline'}
                onClick={() => setDirection('BUY')}
                className={direction === 'BUY' ? 'bg-green-600 hover:bg-green-700' : ''}
              >
                BUY
              </Button>
              <Button 
                variant={direction === 'SELL' ? 'default' : 'outline'}
                onClick={() => setDirection('SELL')}
                className={direction === 'SELL' ? 'bg-red-600 hover:bg-red-700' : ''}
              >
                SELL
              </Button>
            </div>

            <div>
              <Label>Order Type</Label>
              <Select value={orderType} onValueChange={setOrderType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="market">Market</SelectItem>
                  <SelectItem value="limit">Limit</SelectItem>
                  <SelectItem value="stop">Stop</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {orderType !== 'market' && (
              <div>
                <Label>Price</Label>
                <Input 
                  type="number" 
                  placeholder="Entry price"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                />
              </div>
            )}

            <div className="grid grid-cols-3 gap-2">
              <div>
                <Label>Volume</Label>
                <Input 
                  type="number" 
                  step="0.01"
                  value={volume}
                  onChange={(e) => setVolume(parseFloat(e.target.value))}
                />
              </div>
              <div>
                <Label>SL</Label>
                <Input 
                  type="number" 
                  placeholder="SL"
                  value={sl}
                  onChange={(e) => setSl(e.target.value)}
                />
              </div>
              <div>
                <Label>TP</Label>
                <Input 
                  type="number" 
                  placeholder="TP"
                  value={tp}
                  onChange={(e) => setTp(e.target.value)}
                />
              </div>
            </div>

            <Button onClick={handleOrder} className="w-full">
              Execute {direction}
            </Button>
          </CardContent>
        </Card>

        {/* Positions */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Open Positions ({positions.length})</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-muted-foreground">Loading...</p>
            ) : positions.length === 0 ? (
              <p className="text-muted-foreground text-center py-8">No open positions</p>
            ) : (
              <div className="space-y-2">
                {positions.map((pos) => (
                  <div key={pos.ticket} className="flex items-center justify-between p-4 bg-muted rounded-lg">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-bold">{pos.symbol}</span>
                        <span className={`px-2 py-0.5 rounded text-xs ${pos.direction === 'BUY' ? 'bg-green-500/20 text-green-500' : 'bg-red-500/20 text-red-500'}`}>
                          {pos.direction}
                        </span>
                      </div>
                      <div className="text-sm text-muted-foreground mt-1">
                        Vol: {pos.volume} | Entry: {pos.entry_price.toFixed(5)}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`font-bold ${pos.profit >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                        ${pos.profit.toFixed(2)}
                      </div>
                      <Button 
                        variant="destructive" 
                        size="sm" 
                        className="mt-2"
                        onClick={() => handleClose(pos.ticket)}
                      >
                        Close
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}