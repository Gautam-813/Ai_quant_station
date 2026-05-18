import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { Toaster } from '@/components/ui/toaster'

// Layout
import DashboardLayout from '@/components/layout/DashboardLayout'

// Pages
import LoginPage from '@/pages/LoginPage'
import DashboardPage from '@/pages/DashboardPage'
import TerminalPage from '@/pages/TerminalPage'
import AIAnalystPage from '@/pages/AIAnalystPage'
import HistoryPage from '@/pages/HistoryPage'
import HistoricalLabPage from '@/pages/HistoricalLabPage'
import SettingsPage from '@/pages/SettingsPage'
import AutopilotPage from '@/pages/AutopilotPage'
import UserManagementPage from '@/pages/UserManagementPage'
import BacktestPage from '@/pages/BacktestPage'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

function App() {
  const checkAuth = useAuthStore((state) => state.checkAuth)

  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        
        <Route path="/" element={
          <ProtectedRoute>
            <DashboardLayout />
          </ProtectedRoute>
        }>
          <Route index element={<DashboardPage />} />
          <Route path="terminal" element={<TerminalPage />} />
          <Route path="ai-analyst" element={<AIAnalystPage />} />
          <Route path="historical-lab" element={<HistoricalLabPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="autopilot" element={<AutopilotPage />} />
          <Route path="backtest" element={<BacktestPage />} />
          <Route path="users" element={<UserManagementPage />} />
        </Route>
      </Routes>
      <Toaster />
    </BrowserRouter>
  )
}

export default App