import { describe, it, expect } from 'vitest'
import {
  cn,
  formatCurrency,
  formatNumber,
  formatPercent,
  getDirectionColor,
  getProfitColor,
} from '@/utils/utils'

describe('cn', () => {
  it('merges tailwind classes', () => {
    expect(cn('px-4', 'py-2')).toBe('px-4 py-2')
  })

  it('handles conditional classes', () => {
    expect(cn('base', false && 'hidden')).toBe('base')
  })

  it('resolves conflicting classes (last wins)', () => {
    expect(cn('px-4', 'px-6')).toBe('px-6')
  })

  it('accepts array input', () => {
    expect(cn(['a', 'b'])).toBe('a b')
  })
})

describe('formatCurrency', () => {
  it('formats positive number', () => {
    expect(formatCurrency(1234.5)).toBe('$1,234.50')
  })

  it('formats zero', () => {
    expect(formatCurrency(0)).toBe('$0.00')
  })

  it('formats negative number', () => {
    expect(formatCurrency(-500)).toBe('-$500.00')
  })

  it('uses custom currency', () => {
    expect(formatCurrency(100, 'EUR')).toBe('€100.00')
  })
})

describe('formatNumber', () => {
  it('formats with default decimals', () => {
    expect(formatNumber(123.456)).toBe('123.46')
  })

  it('formats with custom decimals', () => {
    expect(formatNumber(123.456, 0)).toBe('123')
  })
})

describe('formatPercent', () => {
  it('formats as percentage', () => {
    expect(formatPercent(0.152)).toBe('15.20%')
  })

  it('formats negative percentage', () => {
    expect(formatPercent(-0.05)).toBe('-5.00%')
  })

  it('handles zero', () => {
    expect(formatPercent(0)).toBe('0.00%')
  })
})

describe('getDirectionColor', () => {
  it('returns green for BUY', () => {
    expect(getDirectionColor('BUY')).toBe('text-green-500')
  })

  it('returns red for SELL', () => {
    expect(getDirectionColor('SELL')).toBe('text-red-500')
  })
})

describe('getProfitColor', () => {
  it('returns green for positive', () => {
    expect(getProfitColor(100)).toBe('text-green-500')
  })

  it('returns green for zero', () => {
    expect(getProfitColor(0)).toBe('text-green-500')
  })

  it('returns red for negative', () => {
    expect(getProfitColor(-1)).toBe('text-red-500')
  })
})
