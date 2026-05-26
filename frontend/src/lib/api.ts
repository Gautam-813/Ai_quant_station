import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
})

api.interceptors.request.use((config) => {
  // JWT token for auth (from zustand persist store)
  try {
    const stored = sessionStorage.getItem('auth-storage')
    if (stored) {
      const parsed = JSON.parse(stored)
      const accessToken = parsed.state?.accessToken
      if (accessToken) {
        config.headers.Authorization = `Bearer ${accessToken}`
      }
    }
  } catch (e) {
    // Ignore parse errors
  }

  return config
})

// 401 token refresh interceptor
let refreshPromise: Promise<void> | null = null

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      try {
        const stored = sessionStorage.getItem('auth-storage')
        if (!stored) return Promise.reject(error)
        const parsed = JSON.parse(stored)
        const refreshToken = parsed.state?.storedRefreshToken
        if (!refreshToken) return Promise.reject(error)

        if (!refreshPromise) {
          refreshPromise = axios.post('/api/auth/refresh', { refresh_token: refreshToken })
            .then(res => {
              const { access_token, refresh_token } = res.data
              const updated = JSON.parse(sessionStorage.getItem('auth-storage') || '{}')
              if (!updated.state) updated.state = {}
              updated.state.accessToken = access_token
              updated.state.storedRefreshToken = refresh_token
              sessionStorage.setItem('auth-storage', JSON.stringify(updated))
            })
            .catch(() => {
              sessionStorage.removeItem('auth-storage')
              window.location.href = '/login'
            })
            .finally(() => { refreshPromise = null })
        }
        await refreshPromise
        return api(error.config)
      } catch {
        return Promise.reject(error)
      }
    }
    return Promise.reject(error)
  }
)

export default api