import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import axios from 'axios'

interface MT5ConnectorSettings {
  useExternal: string  // "true" or "false" for Select
  serverIp: string
  port: string
}

export default function SettingsPage() {
  const { toast } = useToast()
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{success: boolean, message: string} | null>(null)

  // MT5 Connector Settings (persisted in localStorage)
  const [mt5Connector, setMt5Connector] = useState<MT5ConnectorSettings>({
    useExternal: 'false',
    serverIp: '',
    port: '5000'
  })

  // Load saved settings on mount
  useEffect(() => {
    const saved = localStorage.getItem('mt5ConnectorSettings')
    if (saved) {
      setMt5Connector(JSON.parse(saved))
    }
  }, [])

  const saveMt5ConnectorSettings = () => {
    localStorage.setItem('mt5ConnectorSettings', JSON.stringify(mt5Connector))
    const isExternal = mt5Connector.useExternal === 'true'
    toast({
      title: 'MT5 Connector Settings Saved',
      description: isExternal 
        ? `Using external connector: ${mt5Connector.serverIp || 'localhost'}:${mt5Connector.port}`
        : 'Using direct MT5 connection',
    })
  }

  const testMt5Connection = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const headers: Record<string, string> = {
        'x-mt5-token': 'impulse_secure_2026'
      }
      
      // Add connector headers if using external
      if (mt5Connector.useExternal === 'true') {
        let ip = mt5Connector.serverIp.trim()
        // Remove protocol if entered
        ip = ip.replace(/^https?:\/\//, '').replace(/\/$/, '')
        
        const serverUrl = ip 
          ? `http://${ip}:${mt5Connector.port}`
          : `http://localhost:${mt5Connector.port}`
        headers['x-mt5-connector-url'] = serverUrl
      }

      await axios.get('/api/mt5/health', { headers })
      setTestResult({ success: true, message: 'MT5 connection successful!' })
      toast({ title: 'Success', description: 'MT5 connected successfully' })
    } catch (error: any) {
      const msg = error.response?.data?.detail || 'MT5 connection failed'
      setTestResult({ success: false, message: msg })
      toast({ title: 'Error', description: msg, variant: 'destructive' })
    } finally {
      setTesting(false)
    }
  }

  // API Keys (stored in localStorage for demo)
  const [nvidiaKey, setNvidiaKey] = useState('')
  const [groqKey, setGroqKey] = useState('')
  const [openrouterKey, setOpenrouterKey] = useState('')

  const testConnection = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      // Test NVIDIA as default
      await axios.post('/api/ai/test', {
        provider: 'nvidia',
        model: 'qwen/qwen3.5-122b-a10b'
      })
      setTestResult({ success: true, message: 'Connection successful!' })
      toast({ title: 'Success', description: 'AI connection working' })
    } catch (error: any) {
      const errorData = error.response?.data
      let errorMsg = 'Connection failed'
      if (typeof errorData === 'string') {
        errorMsg = errorData
      } else if (errorData?.detail) {
        errorMsg = typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail)
      } else if (errorData?.msg) {
        errorMsg = errorData.msg
      }
      setTestResult({ success: false, message: errorMsg })
      toast({ title: 'Error', description: errorMsg, variant: 'destructive' })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="p-8 max-w-4xl">
      <h1 className="font-heading text-3xl font-bold mb-8">Settings</h1>

      <div className="space-y-6">
        {/* AI Providers */}
        <Card>
          <CardHeader>
            <CardTitle>AI Providers</CardTitle>
            <CardDescription>Configure your AI API keys for different providers</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label>NVIDIA API Key</Label>
              <Input 
                type="password" 
                placeholder="nvapi-xxxxx"
                value={nvidiaKey}
                onChange={(e) => setNvidiaKey(e.target.value)}
              />
            </div>
            <div>
              <Label>Groq API Key</Label>
              <Input 
                type="password" 
                placeholder="gsk_xxxxx"
                value={groqKey}
                onChange={(e) => setGroqKey(e.target.value)}
              />
            </div>
            <div>
              <Label>OpenRouter API Key</Label>
              <Input 
                type="password" 
                placeholder="sk-xxxxx"
                value={openrouterKey}
                onChange={(e) => setOpenrouterKey(e.target.value)}
              />
            </div>
            <Button onClick={testConnection} disabled={testing}>
              {testing ? 'Testing...' : 'Test Connection'}
            </Button>
            {testResult && (
              <div className={`p-3 rounded ${testResult.success ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'}`}>
                {testResult.message}
              </div>
            )}
          </CardContent>
        </Card>

        {/* MT5 Connector */}
        <Card>
          <CardHeader>
            <CardTitle>MT5 Connection</CardTitle>
            <CardDescription>Configure how the backend connects to MT5 Terminal</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Use External Connector</Label>
                <Select 
                  value={mt5Connector.useExternal} 
                  onValueChange={(v) => setMt5Connector({...mt5Connector, useExternal: v})}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="false">No - Direct MT5</SelectItem>
                    <SelectItem value="true">Yes - External Connector</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <p className="text-sm text-muted-foreground">
              Select "Yes" if MT5 Terminal runs on a different computer. Select "No" to connect directly on this machine.
            </p>
            
            {mt5Connector.useExternal === 'true' && (
              <div className="grid grid-cols-2 gap-4 mt-4 p-4 bg-muted rounded-lg">
                <div>
                  <Label>Server IP Address</Label>
                  <Input 
                    placeholder="185.23.23.234 or leave empty for localhost"
                    value={mt5Connector.serverIp}
                    onChange={(e) => setMt5Connector({...mt5Connector, serverIp: e.target.value})}
                  />
                  <p className="text-xs text-muted-foreground mt-1">Leave empty if MT5 is on this PC</p>
                </div>
                <div>
                  <Label>Port Number</Label>
                  <Input 
                    placeholder="5000"
                    value={mt5Connector.port}
                    onChange={(e) => setMt5Connector({...mt5Connector, port: e.target.value})}
                  />
                  <p className="text-xs text-muted-foreground mt-1">Port where MT5 Connector is running</p>
                </div>
              </div>
            )}

            <div className="flex gap-2">
              <Button onClick={saveMt5ConnectorSettings}>
                Save MT5 Settings
              </Button>
              <Button variant="outline" onClick={testMt5Connection} disabled={testing}>
                {testing ? 'Testing...' : 'Test Connection'}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Account */}
        <Card>
          <CardHeader>
            <CardTitle>Account</CardTitle>
            <CardDescription>Manage your account settings</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label>Change Password</Label>
              <Input type="password" placeholder="New password" />
            </div>
            <Button variant="outline">Update Password</Button>
          </CardContent>
        </Card>

        {/* Autopilot */}
        <Card>
          <CardHeader>
            <CardTitle>Autopilot</CardTitle>
            <CardDescription>Configure automated trading settings</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Lot Size</Label>
                <Input type="number" step="0.01" defaultValue="0.10" />
              </div>
              <div>
                <Label>Interval (seconds)</Label>
                <Input type="number" defaultValue="300" />
              </div>
            </div>
            <Button>Save Autopilot Settings</Button>
          </CardContent>
        </Card>

        {/* Data Sync */}
        <Card>
          <CardHeader>
            <CardTitle>Data Sync</CardTitle>
            <CardDescription>HuggingFace and data synchronization</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label>HuggingFace Repo ID</Label>
              <Input placeholder="username/repo" />
            </div>
            <div>
              <Label>HuggingFace Token</Label>
              <Input type="password" placeholder="hf_xxxxx" />
            </div>
            <Button variant="outline">Sync Now</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}