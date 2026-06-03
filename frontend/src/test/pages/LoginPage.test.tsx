import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import LoginPage from '@/pages/LoginPage'
import { useAuthStore } from '@/store/authStore'
import * as toastModule from '@/hooks/use-toast'

vi.mock('axios', () => ({
  default: {
    post: vi.fn(),
    create: vi.fn(() => ({
      post: vi.fn(),
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    })),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}))

function renderLoginPage() {
  return render(
    <BrowserRouter>
      <LoginPage />
    </BrowserRouter>
  )
}

describe('LoginPage', () => {
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

  it('renders the login form', () => {
    renderLoginPage()
    expect(screen.getByText('Welcome back')).toBeInTheDocument()
    expect(screen.getByText('Sign In')).toBeInTheDocument()
    expect(screen.getByLabelText('Username')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
  })

  it('renders the logo and brand name', () => {
    renderLoginPage()
    expect(screen.getByText('The Finance')).toBeInTheDocument()
    expect(screen.getByText('Engine')).toBeInTheDocument()
    expect(screen.getByText('Professional Quant Station')).toBeInTheDocument()
  })

  it('has a submit button that is enabled by default', () => {
    renderLoginPage()
    const submitBtn = screen.getByRole('button', { name: /sign in/i })
    expect(submitBtn).not.toBeDisabled()
  })

  it('renders both input fields as required', () => {
    renderLoginPage()
    expect(screen.getByLabelText('Username')).toHaveAttribute('required')
    expect(screen.getByLabelText('Password')).toHaveAttribute('required')
  })

  it('password input is type password', () => {
    renderLoginPage()
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
  })

  it('shows "Signing in..." when loading', () => {
    useAuthStore.setState({ isLoading: true })
    renderLoginPage()
    expect(screen.getByRole('button', { name: /signing in/i })).toBeDisabled()
  })

  it('calls login and navigates on successful submit', async () => {
    const loginSpy = vi.fn().mockResolvedValue(undefined)
    useAuthStore.setState({ login: loginSpy })

    renderLoginPage()

    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Username'), 'testuser')
    await user.type(screen.getByLabelText('Password'), 'password')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(loginSpy).toHaveBeenCalledWith('testuser', 'password')
  })

  it('shows error toast on submit failure', async () => {
    const toastSpy = vi.fn()
    vi.spyOn(toastModule, 'useToast').mockReturnValue({
      toast: toastSpy,
      toasts: [],
      dismiss: vi.fn(),
    })

    useAuthStore.setState({
      error: 'Invalid credentials',
      login: vi.fn().mockRejectedValue(new Error('Login failed')),
    })

    renderLoginPage()

    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Username'), 'testuser')
    await user.type(screen.getByLabelText('Password'), 'wrong')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Login failed',
          variant: 'destructive',
        })
      )
    })
  })
})
