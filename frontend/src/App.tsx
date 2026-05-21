import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './stores/auth'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import Dashboard from './pages/Dashboard'
import EquipmentList from './pages/EquipmentList'
import RouteList from './pages/RouteList'
import TaskList from './pages/TaskList'
import DefectList from './pages/DefectList'
import Reports from './pages/Reports'
import WorkTicketList from './pages/WorkTicketList'
import OperationTicketList from './pages/OperationTicketList'
import PredictiveMaintenance from './pages/PredictiveMaintenance'
import SparePartList from './pages/SparePartList'
import UserManagement from './pages/UserManagement'
import AuditLog from './pages/AuditLog'
import MobileScan from './pages/MobileScan'
import WorkTicketPrint from './pages/WorkTicketPrint'
import QRPrint from './pages/QRPrint'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <PrivateRoute>
              <Layout />
            </PrivateRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="equipments" element={<EquipmentList />} />
          <Route path="routes" element={<RouteList />} />
          <Route path="tasks" element={<TaskList />} />
          <Route path="defects" element={<DefectList />} />
          <Route path="work-tickets" element={<WorkTicketList />} />
          <Route path="operation-tickets" element={<OperationTicketList />} />
          <Route path="predictive" element={<PredictiveMaintenance />} />
          <Route path="spare-parts" element={<SparePartList />} />
          <Route path="users" element={<UserManagement />} />
          <Route path="audit" element={<AuditLog />} />
          <Route path="reports" element={<Reports />} />
        </Route>
        <Route path="/m/scan" element={<MobileScan />} />
        <Route path="/work-tickets/:id/print" element={<PrivateRoute><WorkTicketPrint /></PrivateRoute>} />
        <Route path="/equipment-qr-print" element={<PrivateRoute><QRPrint /></PrivateRoute>} />
      </Routes>
    </BrowserRouter>
  )
}
