import { useEffect, useRef } from 'react'
import { createChart, LineSeries, ColorType } from 'lightweight-charts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface MiniChartProps {
  title: string
  data: number[]
  color?: string
}

export function MiniChart({ title, data, color = '#2563eb' }: MiniChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!chartContainerRef.current) return

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#d1d5db',
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: '#2a2a2a' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 150,
      handleScale: false,
      handleScroll: false,
      timeScale: {
        visible: false,
      },
      rightPriceScale: {
        borderVisible: false,
      },
    })

    const lineSeries = chart.addSeries(LineSeries, {
      color: color,
      lineWidth: 2,
    })

    const formattedData = data.map((val, i) => ({
      time: i as any,
      value: val,
    }))

    lineSeries.setData(formattedData)
    chart.timeScale().fitContent()

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
    }

    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [data, color])

  return (
    <Card className="mt-3 bg-background/50 border-muted">
      <CardHeader className="py-2 px-3">
        <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div ref={chartContainerRef} className="w-full h-[150px]" />
      </CardContent>
    </Card>
  )
}
