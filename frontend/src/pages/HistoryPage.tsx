import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import axios from 'axios'

interface Trade {
  ticket: number
  symbol: string
  direction: string
  volume: number
  price: number
  profit: number
  time: string
  comment: string
}

export default function HistoryPage() {
  const [trades, setTrades] = useState<Trade[]>([])
  const [loading, setLoading] = useState(true)
  const [hours, setHours] = useState('0')

  useEffect(() => {
    fetchHistory()
  }, [hours])

  const fetchHistory = async () => {
    setLoading(true)
    try {
      const res = await axios.get(`/api/mt5/history?hours=${hours}`)
      setTrades(res.data.deals || [])
    } catch (error) {
      console.error('Failed to fetch history:', error)
    } finally {
      setLoading(false)
    }
  }

  const totalProfit = trades.reduce((sum, t) => sum + t.profit, 0)
  const wins = trades.filter(t => t.profit > 0).length
  const winRate = trades.length > 0 ? (wins / trades.length) * 100 : 0

  return (
    <div className="p-8">
      <h1 className="font-heading text-3xl font-bold mb-8">Trade History</h1>

      {/* Filters */}
      <div className="flex gap-4 mb-6">
        <Select value={hours} onValueChange={setHours}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="0">All Time</SelectItem>
            <SelectItem value="24">Last 24h</SelectItem>
            <SelectItem value="168">Last Week</SelectItem>
            <SelectItem value="720">Last Month</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total P&L</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${totalProfit >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              ${totalProfit.toFixed(2)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Trades</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{trades.length}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Wins</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-500">{wins}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Win Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{winRate.toFixed(1)}%</div>
          </CardContent>
        </Card>
      </div>

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle>Closed Trades</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-muted-foreground">Loading...</p>
          ) : trades.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">No closed trades found</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-3 px-2">Time</th>
                    <th className="text-left py-3 px-2">Symbol</th>
                    <th className="text-left py-3 px-2">Dir</th>
                    <th className="text-right py-3 px-2">Vol</th>
                    <th className="text-right py-3 px-2">Price</th>
                    <th className="text-right py-3 px-2">P&L</th>
                    <th className="text-left py-3 px-2">Comment</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((trade) => (
                    <tr key={trade.ticket} className="border-b border-border hover:bg-muted/50">
                      <td className="py-3 px-2 text-sm">{trade.time}</td>
                      <td className="py-3 px-2 font-medium">{trade.symbol}</td>
                      <td className={`py-3 px-2 ${trade.direction === 'BUY' ? 'text-green-500' : 'text-red-500'}`}>
                        {trade.direction}
                      </td>
                      <td className="py-3 px-2 text-right">{trade.volume}</td>
                      <td className="py-3 px-2 text-right">{trade.price.toFixed(5)}</td>
                      <td className={`py-3 px-2 text-right font-medium ${trade.profit >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                        ${trade.profit.toFixed(2)}
                      </td>
                      <td className="py-3 px-2 text-sm text-muted-foreground">{trade.comment}</td>
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