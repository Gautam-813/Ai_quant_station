import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { useAuthStore } from '@/store/authStore'

// Mock all page imports to avoid complex dependencies
vi.mock('@/pages/LoginPage', () => ({ default: () => <div>Login Page</div> }))
vi.mock('@/pages/DashboardPage', () => ({ default: () => <div>Dashboard</div> }))
vi.mock('@/pages/TerminalPage', () => ({ default: () => <div>Terminal</div> }))
vi.mock('@/pages/AIAnalystPage', () => ({ default: () => <div>AI Analyst</div> }))
vi.mock('@/pages/HistoryPage', () => ({ default: () => <div>History</div> }))
vi.mock('@/pages/HistoricalLabPage', () => ({ default: () => <div>Historical Lab</div> }))
vi.mock('@/pages/SettingsPage', () => ({ default: () => <div>Settings</div> }))
vi.mock('@/pages/AutopilotPage', () => ({ default: () => <div>Autopilot</div> }))
vi.mock('@/pages/UserManagementPage', () => ({ default: () => <div>User Mgmt</div> }))
vi.mock('@/pages/BacktestPage', () => ({ default: () => <div>Backtest</div> }))
vi.mock('@/components/layout/DashboardLayout', () => ({
  default: () => <div>Dashboard Layout</div>,
}))
vi.mock('@/components/ui/toaster', () => ({
  Toaster: () => <div>Toaster</div>,
}))

describe('App', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      accessToken: null,
      storedRefreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
    })
  })

  it('calls checkAuth on mount', async () => {
    const checkAuthSpy = vi.fn()
    useAuthStore.setState({ checkAuth: checkAuthSpy })

    const App = (await import('@/App')).default
    render(<App />)

    expect(checkAuthSpy).toHaveBeenCalledTimes(1)
  })

  it('renders LoginPage at /login route', async () => {
    const App = (await import('@/App')).default

    window.history.pushState({}, '', '/login')
    render(<App />)

    expect(await screen.findByText('Login Page')).toBeInTheDocument()
  })

  it('redirects to /login when not authenticated at / route', async () => {
    const App = (await import('@/App')).default

    window.history.pushState({}, '', '/')
    render(<App />)

    expect(await screen.findByText('Login Page')).toBeInTheDocument()
  })

  it('renders DashboardLayout when authenticated at /', async () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: { id: 1, username: 'admin', name: 'Admin', role: 'admin' },
    })

    const App = (await import('@/App')).default
    window.history.pushState({}, '', '/')
    render(<App />)

    expect(await screen.findByText('Dashboard Layout')).toBeInTheDocument()
  })
})
