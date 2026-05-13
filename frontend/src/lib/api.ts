import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
})

api.interceptors.request.use((config) => {
  config.headers['X-MT5-Token'] = 'impulse_secure_2026'
  return config
})

export default api