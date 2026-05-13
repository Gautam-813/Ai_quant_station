import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import axios from 'axios'

interface User {
  id: number
  username: string
  name: string
  role: string
}

interface AuthState {
  user: User | null
  accessToken: string | null
  storedRefreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
  
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  refreshAccessToken: () => Promise<void>
  checkAuth: () => void
}

const API_URL = '/api/auth'

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      storedRefreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      login: async (username: string, password: string) => {
        set({ isLoading: true, error: null })
        try {
          const response = await axios.post(`${API_URL}/login/test`, {
            username,
            password
          })
          
          const { access_token, refresh_token } = response.data
          
          // Decode JWT to get user info (simple decode)
          const payload = JSON.parse(atob(access_token.split('.')[1]))
          
          set({
            accessToken: access_token,
            storedRefreshToken: refresh_token,
            user: {
              id: payload.user_id,
              username: payload.sub,
              name: payload.sub,
              role: 'trader'
            },
            isAuthenticated: true,
            isLoading: false
          })
        } catch (error: any) {
          set({
            isLoading: false,
            error: error.response?.data?.detail || 'Login failed'
          })
          throw error
        }
      },

      logout: () => {
        set({
          user: null,
          accessToken: null,
          storedRefreshToken: null,
          isAuthenticated: false
        })
      },

      refreshAccessToken: async () => {
        const storedRefreshToken = get().storedRefreshToken
        if (!storedRefreshToken) {
          get().logout()
          return
        }

        try {
          const response = await axios.post(`${API_URL}/refresh`, {
            refresh_token: storedRefreshToken
          })
          
          const { access_token, refresh_token } = response.data
          
          set({
            accessToken: access_token,
            storedRefreshToken: refresh_token
          })
        } catch {
          get().logout()
        }
      },

      checkAuth: () => {
        const { accessToken, storedRefreshToken } = get()
        if (!accessToken || !storedRefreshToken) {
          set({ isAuthenticated: false })
          return
        }

        // Check if token is expired
        try {
          const payload = JSON.parse(atob(accessToken.split('.')[1]))
          const exp = payload.exp * 1000
          const now = Date.now()
          
          if (exp < now) {
            // Token expired, try to refresh
            get().refreshAccessToken()
          } else {
            set({ isAuthenticated: true })
          }
        } catch {
          get().logout()
        }
      }
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        accessToken: state.accessToken,
        storedRefreshToken: state.storedRefreshToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated
      })
    }
  )
)

// Helper to get token from localStorage directly
const getTokenFromStorage = (): string | null => {
  try {
    const stored = localStorage.getItem('auth-storage')
    if (stored) {
      const parsed = JSON.parse(stored)
      return parsed.state?.accessToken || null
    }
  } catch (e) {
    // Ignore
  }
  return null
}

// Axios interceptor for adding auth token
axios.interceptors.request.use((config) => {
  const state = useAuthStore.getState()
  let { accessToken } = state
  
  // Fallback to localStorage if not in state (for initial load)
  if (!accessToken) {
    accessToken = getTokenFromStorage()
  }
  
  // Debug: log the request
  if (config.url?.includes('/mt5')) {
    console.log('MT5 request:', config.url, 'Token exists:', !!accessToken)
  }
  
  // Add JWT token for ALL API calls
  if (accessToken && config.url?.startsWith('/api')) {
    config.headers.Authorization = `Bearer ${accessToken}`
  }
  
  // Add MT5 token for MT5 endpoints
  if (config.url?.includes('/mt5')) {
    config.headers['x-mt5-token'] = 'impulse_secure_2026'
    
    // Add connector URL if configured
    try {
      const savedSettings = localStorage.getItem('mt5ConnectorSettings')
      if (savedSettings) {
        const mt5Settings = JSON.parse(savedSettings)
        if (mt5Settings.useExternal === 'true' && mt5Settings.port) {
          const serverUrl = mt5Settings.serverIp 
            ? `http://${mt5Settings.serverIp}:${mt5Settings.port}`
            : `http://localhost:${mt5Settings.port}`
          config.headers['x-mt5-connector-url'] = serverUrl
        }
      }
    } catch (e) {
      console.error('Error reading MT5 settings:', e)
    }
  }
  return config
})

// Response interceptor for handling 401
axios.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      const storedRefreshToken = useAuthStore.getState().storedRefreshToken
      if (storedRefreshToken) {
        try {
          await useAuthStore.getState().refreshAccessToken()
          // Retry the original request
          return axios(error.config)
        } catch {
          useAuthStore.getState().logout()
        }
      } else {
        useAuthStore.getState().logout()
      }
    }
    return Promise.reject(error)
  }
)