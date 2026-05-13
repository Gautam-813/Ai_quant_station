import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(amount: number, currency: string = "USD"): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency
  }).format(amount)
}

export function formatNumber(num: number, decimals: number = 2): string {
  return num.toFixed(decimals)
}

export function formatPercent(num: number): string {
  return `${(num * 100).toFixed(2)}%`
}

export function getDirectionColor(direction: string): string {
  return direction === 'BUY' ? 'text-green-500' : 'text-red-500'
}

export function getProfitColor(profit: number): string {
  return profit >= 0 ? 'text-green-500' : 'text-red-500'
}