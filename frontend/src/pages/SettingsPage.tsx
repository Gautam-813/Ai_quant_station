import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import axios from 'axios'

interface MT5ConnectorSettings { useExternal: string; serverIp: string; port: string }

export default function SettingsPage() {
  const { toast } = useToast()
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{success: boolean, message: string} | null>(null)
  const [testProvider, setTestProvider] = useState('nvidia')
  const [testModel, setTestModel] = useState('qwen/qwen3.5-122b-a10b')

  const [mt5Connector, setMt5Connector] = useState<MT5ConnectorSettings>({ useExternal: 'false', serverIp: '', port: '5000' })
  useEffect(() => {
    const saved = localStorage.getItem('mt5ConnectorSettings')
    if (saved) setMt5Connector(JSON.parse(saved))
  }, [])

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [passwordLoading, setPasswordLoading] = useState(false)

  const handleChangePassword = async () => {
    if (!currentPassword) { toast({ title: 'Error', description: 'Current password is required', variant: 'destructive' }); return }
    if (!newPassword || newPassword.length < 6) { toast({ title: 'Error', description: 'New password must be at least 6 characters', variant: 'destructive' }); return }
    setPasswordLoading(true)
    try {
      await axios.put('/api/auth/password', { current_password: currentPassword, new_password: newPassword })
      toast({ title: 'Success', description: 'Password changed successfully' })
      setCurrentPassword(''); setNewPassword('')
    } catch (error: any) {
      toast({ title: 'Error', description: error.response?.data?.detail || 'Failed to change password', variant: 'destructive' })
    } finally { setPasswordLoading(false) }
  }

  const [autoLot, setAutoLot] = useState('0.10')
  const [autoInterval, setAutoInterval] = useState('300')

  const handleSaveAutopilot = async () => {
    try {
      await axios.post('/api/autopilot/settings', { default_lot: parseFloat(autoLot), interval_seconds: parseInt(autoInterval), max_trades_per_day: 10, cooldown_minutes: 5, max_daily_loss: -50, symbol: 'XAUUSD', provider: 'nvidia', model: 'qwen/qwen3.5-122b-a10b' })
      toast({ title: 'Success', description: 'Autopilot settings saved' })
    } catch (error: any) { toast({ title: 'Error', description: error.response?.data?.detail || 'Failed to save settings', variant: 'destructive' }) }
  }

  const saveMt5ConnectorSettings = () => {
    localStorage.setItem('mt5ConnectorSettings', JSON.stringify(mt5Connector))
    toast({ title: 'MT5 Connector Settings Saved', description: mt5Connector.useExternal === 'true' ? `Using external: ${mt5Connector.serverIp || 'localhost'}:${mt5Connector.port}` : 'Using direct MT5' })
  }

  const testMt5Connection = async () => {
    setTesting(true); setTestResult(null)
    try {
      const headers: Record<string, string> = { 'x-mt5-token': 'impulse_secure_2026' }
      if (mt5Connector.useExternal === 'true') {
        const ip = mt5Connector.serverIp.trim().replace(/^https?:\/\//, '').replace(/\/$/, '')
        headers['x-mt5-connector-url'] = ip ? `http://${ip}:${mt5Connector.port}` : `http://localhost:${mt5Connector.port}`
      }
      await axios.get('/api/mt5/health', { headers })
      setTestResult({ success: true, message: 'MT5 connection successful!' })
      toast({ title: 'Success', description: 'MT5 connected successfully' })
    } catch (error: any) {
      const msg = error.response?.data?.detail || 'MT5 connection failed'
      setTestResult({ success: false, message: msg })
      toast({ title: 'Error', description: msg, variant: 'destructive' })
    } finally { setTesting(false) }
  }

  const [nvidiaKey, setNvidiaKey] = useState(() => localStorage.getItem('nvidia_api_key') || '')
  const [groqKey, setGroqKey] = useState(() => localStorage.getItem('groq_api_key') || '')
  const [openrouterKey, setOpenrouterKey] = useState(() => localStorage.getItem('openrouter_api_key') || '')
  const [availableProviders, setAvailableProviders] = useState<{id: string, name: string, models: string[]}[]>([])
  useEffect(() => { axios.get('/api/ai/providers').then(res => setAvailableProviders(res.data.providers || [])).catch(() => {}) }, [])
  useEffect(() => {
    const prov = availableProviders.find(p => p.id === testProvider)
    if (prov?.models?.length) setTestModel(prov.models[0])
  }, [testProvider, availableProviders])

  const testConnection = async () => {
    setTesting(true); setTestResult(null)
    try {
      await axios.post('/api/ai/test', { provider: testProvider, model: testModel })
      setTestResult({ success: true, message: `Connection to ${testProvider} successful!` })
      toast({ title: 'Success', description: 'AI connection working' })
    } catch (error: any) { setTestResult({ success: false, message: error.response?.data?.detail || 'Connection failed' }); toast({ title: 'Error', description: 'Connection failed', variant: 'destructive' }) }
    finally { setTesting(false) }
  }

  return (
    <div className="p-3 sm:p-6 md:p-8 max-w-4xl mx-auto">
      <h1 className="font-heading text-xl sm:text-2xl md:text-3xl font-bold mb-4 sm:mb-6 md:mb-8">Settings</h1>

      <div className="space-y-4 sm:space-y-6">
        {/* Account */}
        <Card>
          <CardHeader className="px-3 sm:px-4 md:px-6 pt-3 sm:pt-4 md:pt-6 pb-2 sm:pb-3">
            <CardTitle className="text-sm sm:text-base md:text-lg">Account</CardTitle>
            <CardDescription className="text-xs sm:text-sm">Change your password</CardDescription>
          </CardHeader>
          <CardContent className="px-3 sm:px-4 md:px-6 pb-3 sm:pb-4 md:pb-6 space-y-3 sm:space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
              <div>
                <Label className="text-xs sm:text-sm">Current Password</Label>
                <Input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} placeholder="Current password" className="text-sm h-9 sm:h-10" />
              </div>
              <div>
                <Label className="text-xs sm:text-sm">New Password</Label>
                <Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="Min 6 chars" className="text-sm h-9 sm:h-10" />
              </div>
            </div>
            <Button variant="outline" onClick={handleChangePassword} disabled={passwordLoading} className="text-xs sm:text-sm w-full sm:w-auto">
              {passwordLoading ? 'Updating...' : 'Update Password'}
            </Button>
          </CardContent>
        </Card>

        {/* AI Providers */}
        <Card>
          <CardHeader className="px-3 sm:px-4 md:px-6 pt-3 sm:pt-4 md:pt-6 pb-2 sm:pb-3">
            <CardTitle className="text-sm sm:text-base md:text-lg">AI Providers</CardTitle>
            <CardDescription className="text-xs sm:text-sm">Configure your AI API keys</CardDescription>
          </CardHeader>
          <CardContent className="px-3 sm:px-4 md:px-6 pb-3 sm:pb-4 md:pb-6 space-y-3 sm:space-y-4">
            <div className="space-y-3 sm:space-y-4">
              {[
                { label: 'NVIDIA API Key', value: nvidiaKey, setter: setNvidiaKey, placeholder: 'nvapi-xxxxx' },
                { label: 'Groq API Key', value: groqKey, setter: setGroqKey, placeholder: 'gsk_xxxxx' },
                { label: 'OpenRouter API Key', value: openrouterKey, setter: setOpenrouterKey, placeholder: 'sk-xxxxx' },
              ].map(({ label, value, setter, placeholder }) => (
                <div key={label}>
                  <Label className="text-xs sm:text-sm">{label}</Label>
                  <Input type="password" value={value} onChange={(e) => setter(e.target.value)} placeholder={placeholder} className="text-sm h-9 sm:h-10 bg-background" />
                </div>
              ))}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
              <div>
                <Label className="text-xs sm:text-sm">Provider</Label>
                <Select value={testProvider} onValueChange={setTestProvider}>
                  <SelectTrigger className="text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {availableProviders.map((p) => (<SelectItem key={p.id} value={p.id} className="text-sm">{p.name}</SelectItem>))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs sm:text-sm">Model</Label>
                <Select value={testModel} onValueChange={setTestModel}>
                  <SelectTrigger className="text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {availableProviders.find(p => p.id === testProvider)?.models.map((m) => (
                      <SelectItem key={m} value={m} className="text-sm text-xs">{m.length > 25 ? m.substring(0, 25) + '...' : m}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex flex-col sm:flex-row gap-2">
              <Button onClick={() => { localStorage.setItem('nvidia_api_key', nvidiaKey); localStorage.setItem('groq_api_key', groqKey); localStorage.setItem('openrouter_api_key', openrouterKey); toast({ title: 'Success', description: 'API keys saved locally' }) }} size="sm" className="text-xs sm:text-sm">Save Keys</Button>
              <Button onClick={testConnection} disabled={testing} variant="outline" size="sm" className="text-xs sm:text-sm">{testing ? 'Testing...' : 'Test Connection'}</Button>
            </div>
            {testResult && (
              <div className={`p-2 sm:p-3 rounded text-xs sm:text-sm ${testResult.success ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'}`}>
                {testResult.message}
              </div>
            )}
          </CardContent>
        </Card>

        {/* MT5 Connector */}
        <Card>
          <CardHeader className="px-3 sm:px-4 md:px-6 pt-3 sm:pt-4 md:pt-6 pb-2 sm:pb-3">
            <CardTitle className="text-sm sm:text-base md:text-lg">MT5 Connection</CardTitle>
            <CardDescription className="text-xs sm:text-sm">Configure MT5 Terminal connection</CardDescription>
          </CardHeader>
          <CardContent className="px-3 sm:px-4 md:px-6 pb-3 sm:pb-4 md:pb-6 space-y-3 sm:space-y-4">
            <div className="w-full sm:w-64">
              <Label className="text-xs sm:text-sm">Use External Connector</Label>
              <Select value={mt5Connector.useExternal} onValueChange={(v) => setMt5Connector({...mt5Connector, useExternal: v})}>
                <SelectTrigger className="text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="false">No - Direct MT5</SelectItem>
                  <SelectItem value="true">Yes - External Connector</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {mt5Connector.useExternal === 'true' && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4 p-3 sm:p-4 bg-muted rounded-lg">
                <div>
                  <Label className="text-xs sm:text-sm">Server IP</Label>
                  <Input placeholder="IP or leave empty for localhost" value={mt5Connector.serverIp} onChange={(e) => setMt5Connector({...mt5Connector, serverIp: e.target.value})} className="text-sm h-9 sm:h-10" />
                </div>
                <div>
                  <Label className="text-xs sm:text-sm">Port</Label>
                  <Input placeholder="5000" value={mt5Connector.port} onChange={(e) => setMt5Connector({...mt5Connector, port: e.target.value})} className="text-sm h-9 sm:h-10" />
                </div>
              </div>
            )}
            <div className="flex flex-col sm:flex-row gap-2">
              <Button onClick={saveMt5ConnectorSettings} size="sm" className="text-xs sm:text-sm">Save MT5 Settings</Button>
              <Button variant="outline" onClick={testMt5Connection} disabled={testing} size="sm" className="text-xs sm:text-sm">{testing ? 'Testing...' : 'Test Connection'}</Button>
            </div>
          </CardContent>
        </Card>

        {/* Autopilot */}
        <Card>
          <CardHeader className="px-3 sm:px-4 md:px-6 pt-3 sm:pt-4 md:pt-6 pb-2 sm:pb-3">
            <CardTitle className="text-sm sm:text-base md:text-lg">Autopilot</CardTitle>
            <CardDescription className="text-xs sm:text-sm">Automated trading settings</CardDescription>
          </CardHeader>
          <CardContent className="px-3 sm:px-4 md:px-6 pb-3 sm:pb-4 md:pb-6 space-y-3 sm:space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
              <div>
                <Label className="text-xs sm:text-sm">Lot Size</Label>
                <Input type="number" step="0.01" value={autoLot} onChange={(e) => setAutoLot(e.target.value)} className="text-sm h-9 sm:h-10" />
              </div>
              <div>
                <Label className="text-xs sm:text-sm">Interval (seconds)</Label>
                <Input type="number" value={autoInterval} onChange={(e) => setAutoInterval(e.target.value)} className="text-sm h-9 sm:h-10" />
              </div>
            </div>
            <Button onClick={handleSaveAutopilot} size="sm" className="text-xs sm:text-sm w-full sm:w-auto">Save Autopilot Settings</Button>
          </CardContent>
        </Card>

        {/* Data Sync */}
        <Card>
          <CardHeader className="px-3 sm:px-4 md:px-6 pt-3 sm:pt-4 md:pt-6 pb-2 sm:pb-3">
            <CardTitle className="text-sm sm:text-base md:text-lg">Data Sync</CardTitle>
            <CardDescription className="text-xs sm:text-sm">HuggingFace data synchronization</CardDescription>
          </CardHeader>
          <CardContent className="px-3 sm:px-4 md:px-6 pb-3 sm:pb-4 md:pb-6 space-y-3 sm:space-y-4">
            <div>
              <Label className="text-xs sm:text-sm">HuggingFace Repo ID</Label>
              <Input placeholder="username/repo" className="text-sm h-9 sm:h-10" />
            </div>
            <div>
              <Label className="text-xs sm:text-sm">HuggingFace Token</Label>
              <Input type="password" placeholder="hf_xxxxx" className="text-sm h-9 sm:h-10" />
            </div>
            <Button variant="outline" size="sm" className="text-xs sm:text-sm">Sync Now</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
