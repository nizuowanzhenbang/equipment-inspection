import { create } from 'zustand'

export type Role = 'ADMIN' | 'INSPECTOR' | 'REPAIRMAN' | 'SUPERVISOR' | 'VIEWER'

interface AuthState {
  token: string | null
  username: string | null
  role: string | null
  setAuth: (token: string, username: string, role: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem('token'),
  username: localStorage.getItem('username'),
  role: localStorage.getItem('role'),
  setAuth: (token, username, role) => {
    localStorage.setItem('token', token)
    localStorage.setItem('username', username)
    localStorage.setItem('role', role)
    set({ token, username, role })
  },
  logout: () => {
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    localStorage.removeItem('role')
    set({ token: null, username: null, role: null })
  },
}))

export const canInspect = (role: string | null) =>
  role === 'ADMIN' || role === 'INSPECTOR'

export const canRepair = (role: string | null) =>
  role === 'ADMIN' || role === 'REPAIRMAN'

export const canSupervise = (role: string | null) =>
  role === 'ADMIN' || role === 'SUPERVISOR'

export const canWrite = (role: string | null) => role !== 'VIEWER' && role !== null

export const ROLE_LABEL: Record<string, string> = {
  ADMIN: '管理员',
  INSPECTOR: '点检员',
  REPAIRMAN: '维修工',
  SUPERVISOR: '设备主管',
  VIEWER: '查看者',
}
