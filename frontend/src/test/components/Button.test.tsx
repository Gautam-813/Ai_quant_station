import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Button } from '@/components/ui/button'

describe('Button', () => {
  it('renders children text', () => {
    render(<Button>Click me</Button>)
    expect(screen.getByText('Click me')).toBeInTheDocument()
  })

  it('applies default variant classes', () => {
    render(<Button>Default</Button>)
    const btn = screen.getByText('Default')
    expect(btn.className).toContain('bg-primary')
  })

  it('applies destructive variant', () => {
    render(<Button variant="destructive">Delete</Button>)
    const btn = screen.getByText('Delete')
    expect(btn.className).toContain('bg-destructive')
  })

  it('applies outline variant', () => {
    render(<Button variant="outline">Outline</Button>)
    const btn = screen.getByText('Outline')
    expect(btn.className).toContain('border-input')
  })

  it('applies size classes', () => {
    render(<Button size="lg">Large</Button>)
    const btn = screen.getByText('Large')
    expect(btn.className).toContain('h-11')
  })

  it('fires onClick handler', () => {
    const handleClick = vi.fn()
    render(<Button onClick={handleClick}>Click</Button>)
    fireEvent.click(screen.getByText('Click'))
    expect(handleClick).toHaveBeenCalledOnce()
  })

  it('is disabled when disabled prop is set', () => {
    render(<Button disabled>Disabled</Button>)
    const btn = screen.getByText('Disabled') as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })

  it('does not fire onClick when disabled', () => {
    const handleClick = vi.fn()
    render(<Button disabled onClick={handleClick}>Disabled</Button>)
    fireEvent.click(screen.getByText('Disabled'))
    expect(handleClick).not.toHaveBeenCalled()
  })

  it('forwards additional HTML attributes', () => {
    render(<Button data-testid="test-btn" type="submit">Submit</Button>)
    const btn = screen.getByTestId('test-btn')
    expect(btn.getAttribute('type')).toBe('submit')
  })

  it('renders as child element with asChild', () => {
    render(
      <Button asChild>
        <a href="/test">Link</a>
      </Button>
    )
    const link = screen.getByText('Link')
    expect(link.tagName).toBe('A')
    expect(link.getAttribute('href')).toBe('/test')
  })
})
