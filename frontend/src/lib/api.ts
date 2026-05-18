import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
})

api.interceptors.request.use((config) => {
  const mt5Token = localStorage.getItem('mt5_api_token') || ''
  if (mt5Token) {
    config.headers['X-MT5-Token'] = mt5Token
  }
  return config
})

export default api