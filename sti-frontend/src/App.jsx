import { Link, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Patients from './pages/Patients'
import PatientDetail from './pages/PatientDetail'
import RiskAssessment from './pages/RiskAssessment'
import PredictionResult from './pages/PredictionResult'
import Heatmap from './pages/Heatmap'
import Reports from './pages/Reports'
import MLModels from './pages/MLModels'
import AuditLogs from './pages/AuditLogs'
import Settings from './pages/Settings'
import LandingPage from './pages/LandingPage'
import { EmptyState } from './components/States'

function NotFound() {
  return (
    <EmptyState
      title="Page not found"
      description="That page doesn't exist. It may have been moved or renamed."
      action={<Link to="/dashboard" className="btn-primary">Back to dashboard</Link>}
    />
  )
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route element={<Layout />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/patients" element={<Patients />} />
        <Route path="/patients/:id" element={<PatientDetail />} />
        <Route path="/assess" element={<RiskAssessment />} />
        <Route path="/assess/result/:predictionId" element={<PredictionResult />} />
        <Route path="/heatmap" element={<Heatmap />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/models" element={<MLModels />} />
        <Route path="/audit" element={<AuditLogs />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}

export default App
