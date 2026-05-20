import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import { useHistoryStore } from '@/store/historyStore'
import axios from 'axios'

interface Trade { ticket: number; symbol: string; direction: string; volume: number; price: number; profit: number; time: string; comment: string }

export default function HistoryPage() {
  const { toast } = useToast()
  const [trades, setTrades] = useState<Trade[]>([])
  const [loading, setLoading] = useState(true)
  const hours = useHistoryStore((s) => s.hours)
  const setHours = useHistoryStore((s) => s.setHours)

  useEffect(() => { fetchHistory() }, [hours])

  const fetchHistory = async () => {
    setLoading(true)
    try { setTrades((await axios.get(`/api/mt5/history?hours=${hours}`)).data?.deals || []) }
    catch { toast({ title: "Error", description: "Failed to fetch trade history", variant: 'destructive' }) }
    finally { setLoading(false) }
  }

  const totalProfit = trades.reduce((sum, t) => sum + t.profit, 0)
  const wins = trades.filter(t => t.profit > 0).length
  const winRate = trades.length > 0 ? (wins / trades.length) * 100 : 0

  return (
    <div className="p-3 sm:p-6 md:p-8">
      <h1 className="font-heading text-xl sm:text-2xl md:text-3xl font-bold mb-4 sm:mb-6 md:mb-8">Trade History</h1>

      <div className="flex flex-wrap gap-2 sm:gap-4 mb-4 sm:mb-6">
        <Select value={hours} onValueChange={setHours}>
          <SelectTrigger className="w-32 sm:w-40 text-sm"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="0">All Time</SelectItem>
            <SelectItem value="24">Last 24h</SelectItem>
            <SelectItem value="168">Last Week</SelectItem>
            <SelectItem value="720">Last Month</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-4 mb-4 sm:mb-6 md:mb-8">
        <Card>
          <CardHeader className="pb-1 px-3 pt-3 sm:px-4 sm:pt-4">
            <CardTitle className="text-[10px] sm:text-xs md:text-sm font-medium text-muted-foreground">Total P&L</CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3 sm:px-4 sm:pb-4">
            <div className={`text-sm sm:text-lg md:text-2xl font-bold ${totalProfit >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              ${totalProfit.toFixed(2)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1 px-3 pt-3 sm:px-4 sm:pt-4">
            <CardTitle className="text-[10px] sm:text-xs md:text-sm font-medium text-muted-foreground">Total Trades</CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3 sm:px-4 sm:pb-4">
            <div className="text-sm sm:text-lg md:text-2xl font-bold">{trades.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1 px-3 pt-3 sm:px-4 sm:pt-4">
            <CardTitle className="text-[10px] sm:text-xs md:text-sm font-medium text-muted-foreground">Wins</CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3 sm:px-4 sm:pb-4">
            <div className="text-sm sm:text-lg md:text-2xl font-bold text-green-500">{wins}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1 px-3 pt-3 sm:px-4 sm:pt-4">
            <CardTitle className="text-[10px] sm:text-xs md:text-sm font-medium text-muted-foreground">Win Rate</CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3 sm:px-4 sm:pb-4">
            <div className="text-sm sm:text-lg md:text-2xl font-bold">{winRate.toFixed(1)}%</div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="px-3 sm:px-4 md:px-6 pt-3 sm:pt-4 md:pt-6 pb-2 sm:pb-3">
          <CardTitle className="text-sm sm:text-base md:text-lg">Closed Trades</CardTitle>
        </CardHeader>
        <CardContent className="px-3 sm:px-4 md:px-6 pb-3 sm:pb-4 md:pb-6">
          {loading ? (
            <p className="text-muted-foreground text-center py-6 sm:py-8 text-sm">Loading...</p>
          ) : trades.length === 0 ? (
            <p className="text-muted-foreground text-center py-6 sm:py-8 text-sm">No closed trades found</p>
          ) : (
            <div className="overflow-x-auto -mx-3 sm:mx-0">
              <table className="w-full text-xs sm:text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-2 px-1 sm:px-2 font-medium text-muted-foreground">Time</th>
                    <th className="text-left py-2 px-1 sm:px-2 font-medium text-muted-foreground">Symbol</th>
                    <th className="text-left py-2 px-1 sm:px-2 font-medium text-muted-foreground hidden sm:table-cell">Dir</th>
                    <th className="text-right py-2 px-1 sm:px-2 font-medium text-muted-foreground">Vol</th>
                    <th className="text-right py-2 px-1 sm:px-2 font-medium text-muted-foreground hidden md:table-cell">Price</th>
                    <th className="text-right py-2 px-1 sm:px-2 font-medium text-muted-foreground">P&L</th>
                    <th className="text-left py-2 px-1 sm:px-2 font-medium text-muted-foreground hidden lg:table-cell">Comment</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((trade) => (
                    <tr key={trade.ticket} className="border-b border-border/50 hover:bg-muted/50">
                      <td className="py-2 px-1 sm:px-2 text-[10px] sm:text-xs whitespace-nowrap">{trade.time}</td>
                      <td className="py-2 px-1 sm:px-2 font-medium">{trade.symbol}</td>
                      <td className={`py-2 px-1 sm:px-2 hidden sm:table-cell ${trade.direction === 'BUY' ? 'text-green-500' : 'text-red-500'}`}>{trade.direction}</td>
                      <td className="py-2 px-1 sm:px-2 text-right">{trade.volume}</td>
                      <td className="py-2 px-1 sm:px-2 text-right hidden md:table-cell">{(trade.price || 0).toFixed(5)}</td>
                      <td className={`py-2 px-1 sm:px-2 text-right font-medium ${(trade.profit ?? 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                        ${(trade.profit ?? 0).toFixed(2)}
                      </td>
                      <td className="py-2 px-1 sm:px-2 text-xs text-muted-foreground truncate max-w-[80px] sm:max-w-[150px] hidden lg:table-cell">{trade.comment}</td>
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
