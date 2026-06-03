import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'

describe('Card', () => {
  it('renders Card with children', () => {
    render(<Card><p>content</p></Card>)
    expect(screen.getByText('content')).toBeInTheDocument()
  })

  it('renders Card with custom className', () => {
    const { container } = render(<Card className="custom-class"><p>content</p></Card>)
    expect(container.firstChild).toHaveClass('custom-class')
  })

  it('renders CardHeader', () => {
    render(<CardHeader><h2>Header</h2></CardHeader>)
    expect(screen.getByText('Header')).toBeInTheDocument()
  })

  it('renders CardTitle', () => {
    render(<CardTitle>Title</CardTitle>)
    const el = screen.getByText('Title')
    expect(el.tagName).toBe('H3')
  })

  it('renders CardDescription', () => {
    render(<CardDescription>Description</CardDescription>)
    expect(screen.getByText('Description')).toBeInTheDocument()
  })

  it('renders CardContent', () => {
    render(<CardContent><span>content</span></CardContent>)
    expect(screen.getByText('content')).toBeInTheDocument()
  })

  it('renders CardFooter', () => {
    render(<CardFooter><span>footer</span></CardFooter>)
    expect(screen.getByText('footer')).toBeInTheDocument()
  })

  it('renders compound Card structure', () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>My Card</CardTitle>
          <CardDescription>My Description</CardDescription>
        </CardHeader>
        <CardContent>Body content</CardContent>
        <CardFooter>Footer content</CardFooter>
      </Card>
    )
    expect(screen.getByText('My Card')).toBeInTheDocument()
    expect(screen.getByText('My Description')).toBeInTheDocument()
    expect(screen.getByText('Body content')).toBeInTheDocument()
    expect(screen.getByText('Footer content')).toBeInTheDocument()
  })

  it('applies base card classes', () => {
    const { container } = render(<Card><p>test</p></Card>)
    expect(container.firstChild).toHaveClass('rounded-lg', 'border', 'shadow-sm')
  })
})
