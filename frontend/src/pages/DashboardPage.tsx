import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useEffect, useState } from 'react'
import axios from 'axios'

interface AccountInfo {
  balance: number
  equity: number
  margin: number
  free_margin: number
  margin_level: number
  profit: number
}

interface Position {
  ticket: number
  symbol: string
  direction: string
  volume: number
  profit: number
}

export default function DashboardPage() {
  const [account, setAccount] = useState<AccountInfo | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Get positions (includes account info)
        const posRes = await axios.get('/api/mt5/positions')
        setAccount({
          balance: posRes.data.balance,
          equity: posRes.data.equity,
          margin: posRes.data.margin,
          free_margin: posRes.data.free_margin,
          margin_level: posRes.data.margin_level,
          profit: posRes.data.total_profit
        })
        setPositions(posRes.data.positions || [])
      } catch (error) {
        console.error('Failed to fetch data:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [])

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[400px]">
        <div className="text-muted-foreground">Loading dashboard...</div>
      </div>
    )
  }

  return (
    <div className="p-8">
      <h1 className="font-heading text-3xl font-bold mb-8">Dashboard</h1>

      {/* Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Balance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              ${account?.balance?.toFixed(2) || '0.00'}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Equity</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              ${account?.equity?.toFixed(2) || '0.00'}
            </div>
            <div className={`text-sm ${(account?.profit || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {account?.profit ? `$${account.profit.toFixed(2)}` : '$0.00'}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Margin</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              ${account?.margin?.toFixed(2) || '0.00'}
            </div>
            <div className="text-sm text-muted-foreground">
              Free: ${account?.free_margin?.toFixed(2) || '0.00'}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Margin Level</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {account?.margin_level?.toFixed(1) || '0'}%
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Open Positions */}
      <Card>
        <CardHeader>
          <CardTitle>Open Positions ({positions.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {positions.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">
              No open positions. Start trading in the Terminal.
            </p>
          ) : (
            <div className="space-y-2">
              {positions.map((pos) => (
                <div key={pos.ticket} className="flex items-center justify-between p-3 bg-muted rounded-lg">
                  <div>
                    <span className="font-medium">{pos.symbol}</span>
                    <span className={`ml-2 ${pos.direction === 'BUY' ? 'text-green-500' : 'text-red-500'}`}>
                      {pos.direction}
                    </span>
                    <span className="ml-2 text-muted-foreground">×{pos.volume}</span>
                  </div>
                  <div className={pos.profit >= 0 ? 'text-green-500' : 'text-red-500'}>
                    ${pos.profit.toFixed(2)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}