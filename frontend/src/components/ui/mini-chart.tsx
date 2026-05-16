import { useEffect, useRef, useState } from 'react'
import { createChart, LineSeries, ColorType } from 'lightweight-charts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface MiniChartProps {
  title: string
  data: number[]
  color?: string
}

export function MiniChart({ title, data, color = '#2563eb' }: MiniChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const [isExpanded, setIsExpanded] = useState(false)
  const chartRef = useRef<any>(null)

  useEffect(() => {
    if (!chartContainerRef.current) return

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#d1d5db',
      },
      grid: {
        vertLines: { color: '#2a2a2a' },
        horzLines: { color: '#2a2a2a' },
      },
      width: chartContainerRef.current.clientWidth,
      height: isExpanded ? 400 : 150,
      handleScale: true,
      handleScroll: true,
      timeScale: {
        visible: true,
        borderVisible: false,
        timeVisible: true,
      },
      rightPriceScale: {
        borderVisible: false,
      },
      crosshair: {
        vertLine: {
          color: '#4b5563',
          width: 1,
          style: 2,
          labelBackgroundColor: '#1f2937',
        },
        horzLine: {
          color: '#4b5563',
          width: 1,
          style: 2,
          labelBackgroundColor: '#1f2937',
        },
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
    chartRef.current = chart

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
      <CardHeader className="py-2 px-3 flex flex-row items-center justify-between">
        <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          {title}
        </CardTitle>
        <button 
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-[10px] text-primary hover:underline"
        >
          {isExpanded ? 'Collapse' : 'Expand'}
        </button>
      </CardHeader>
      <CardContent className="p-0">
        <div ref={chartContainerRef} style={{ height: isExpanded ? '400px' : '150px' }} className="w-full" />
      </CardContent>
    </Card>
  )
}
