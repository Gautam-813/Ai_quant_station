import { useState, useEffect } from 'react'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useToast } from '@/hooks/use-toast'
import axios from 'axios'

interface User { id: number; username: string; name: string; role: string; is_active: boolean; created_at: string; last_login: string | null }

export default function UserManagementPage() {
  const { accessToken } = useAuthStore()
  const { toast } = useToast()
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [formData, setFormData] = useState({ username: '', name: '', password: '', role: 'trader' })

  const API_URL = '/api/auth'

  useEffect(() => { fetchUsers() }, [accessToken])

  const fetchUsers = async () => {
    try { setUsers((await axios.get(`${API_URL}/users`, { headers: { Authorization: `Bearer ${accessToken}` } })).data) }
    catch { console.error('Error fetching users') }
    finally { setLoading(false) }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      if (editingUser) {
        await axios.put(`${API_URL}/users/${editingUser.id}`, { name: formData.name, role: formData.role, password: formData.password || undefined }, { headers: { Authorization: `Bearer ${accessToken}` } })
        toast({ title: 'User updated' })
      } else {
        await axios.post(`${API_URL}/users`, formData, { headers: { Authorization: `Bearer ${accessToken}` } })
        toast({ title: 'User created' })
      }
      setShowModal(false); setFormData({ username: '', name: '', password: '', role: 'trader' }); setEditingUser(null); fetchUsers()
    } catch (error: any) { toast({ title: 'Failed', description: error.response?.data?.detail || 'Error', variant: 'destructive' }) }
  }

  return (
    <div className="p-3 sm:p-6 md:p-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 sm:mb-6 md:mb-8">
        <h1 className="font-heading text-xl sm:text-2xl md:text-3xl font-bold">User Management</h1>
        <Button size="sm" onClick={() => { setEditingUser(null); setFormData({ username: '', name: '', password: '', role: 'trader' }); setShowModal(true) }} className="text-xs sm:text-sm w-full sm:w-auto">
          Add User
        </Button>
      </div>

      <Card>
        <CardHeader className="px-3 sm:px-4 md:px-6 pt-3 sm:pt-4 md:pt-6 pb-2 sm:pb-3">
          <CardTitle className="text-sm sm:text-base md:text-lg">Users ({users.length})</CardTitle>
        </CardHeader>
        <CardContent className="px-3 sm:px-4 md:px-6 pb-3 sm:pb-4 md:pb-6">
          {loading ? (
            <p className="text-muted-foreground text-center py-6 sm:py-8 text-sm">Loading...</p>
          ) : (
            <div className="overflow-x-auto -mx-3 sm:mx-0">
              <table className="w-full text-xs sm:text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-2 px-1 sm:px-2 font-medium text-muted-foreground">Username</th>
                    <th className="text-left py-2 px-1 sm:px-2 font-medium text-muted-foreground hidden sm:table-cell">Name</th>
                    <th className="text-left py-2 px-1 sm:px-2 font-medium text-muted-foreground">Role</th>
                    <th className="text-left py-2 px-1 sm:px-2 font-medium text-muted-foreground hidden md:table-cell">Status</th>
                    <th className="text-left py-2 px-1 sm:px-2 font-medium text-muted-foreground hidden lg:table-cell">Last Login</th>
                    <th className="text-right py-2 px-1 sm:px-2 font-medium text-muted-foreground">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id} className="border-b border-border/50 hover:bg-muted/50">
                      <td className="py-2 px-1 sm:px-2 font-medium">{user.username}</td>
                      <td className="py-2 px-1 sm:px-2 text-muted-foreground hidden sm:table-cell">{user.name}</td>
                      <td className="py-2 px-1 sm:px-2">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] sm:text-xs ${
                          user.role === 'admin' ? 'bg-purple-600' : user.role === 'trader' ? 'bg-blue-600' : 'bg-gray-600'
                        }`}>{user.role}</span>
                      </td>
                      <td className="py-2 px-1 sm:px-2 hidden md:table-cell">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] sm:text-xs ${user.is_active ? 'bg-green-600' : 'bg-red-600'}`}>
                          {user.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="py-2 px-1 sm:px-2 text-muted-foreground text-[10px] sm:text-xs hidden lg:table-cell">
                        {user.last_login ? new Date(user.last_login).toLocaleDateString() : 'Never'}
                      </td>
                      <td className="py-2 px-1 sm:px-2 text-right">
                        <div className="flex justify-end gap-1">
                          <Button size="sm" variant="ghost" onClick={() => { setEditingUser(user); setFormData({ username: user.username, name: user.name, password: '', role: user.role }); setShowModal(true) }} className="text-[10px] sm:text-xs h-7 px-1.5 sm:px-2">Edit</Button>
                          <Button size="sm" variant="ghost" className="text-[10px] sm:text-xs text-red-500 h-7 px-1.5 sm:px-2"
                            onClick={async () => { if (confirm('Delete user?')) { await axios.delete(`${API_URL}/users/${user.id}`, { headers: { Authorization: `Bearer ${accessToken}` } }); fetchUsers(); toast({ title: 'User deleted' }) }}}>
                            Del
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-3 sm:p-4" onClick={() => setShowModal(false)}>
          <div className="bg-card border border-border rounded-xl w-full max-w-sm sm:max-w-md p-4 sm:p-6 shadow-xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h2 className="font-heading font-bold text-base sm:text-lg mb-4">{editingUser ? 'Edit User' : 'Add User'}</h2>
            <form onSubmit={handleSubmit} className="space-y-3 sm:space-y-4">
              <div>
                <Label className="text-xs sm:text-sm">Username</Label>
                <Input value={formData.username} onChange={(e) => setFormData({...formData, username: e.target.value})} required={!editingUser} disabled={!!editingUser} className="text-sm h-9 sm:h-10" />
              </div>
              <div>
                <Label className="text-xs sm:text-sm">Name</Label>
                <Input value={formData.name} onChange={(e) => setFormData({...formData, name: e.target.value})} required className="text-sm h-9 sm:h-10" />
              </div>
              <div>
                <Label className="text-xs sm:text-sm">{editingUser ? 'New Password (leave blank to keep)' : 'Password'}</Label>
                <Input type="password" value={formData.password} onChange={(e) => setFormData({...formData, password: e.target.value})} required={!editingUser} className="text-sm h-9 sm:h-10" />
              </div>
              <div>
                <Label className="text-xs sm:text-sm">Role</Label>
                <Select value={formData.role} onValueChange={(v) => setFormData({...formData, role: v})}>
                  <SelectTrigger className="text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="admin">Admin</SelectItem>
                    <SelectItem value="trader">Trader</SelectItem>
                    <SelectItem value="viewer">Viewer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex gap-2 sm:gap-3 pt-2">
                <Button type="button" variant="outline" onClick={() => setShowModal(false)} className="flex-1 text-sm">Cancel</Button>
                <Button type="submit" className="flex-1 text-sm">{editingUser ? 'Update' : 'Create'}</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
