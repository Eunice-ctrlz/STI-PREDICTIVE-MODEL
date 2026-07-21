import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { User, Activity, Clock, ShieldAlert, ArrowLeft } from 'lucide-react'
import { api } from '../lib/api'
import { formatDate } from '../lib/utils'

export default function PatientDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [patient, setPatient] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadPatientData()
  }, [id])

  const loadPatientData = async () => {
    setLoading(true)
    try {
      const [patRes, histRes] = await Promise.all([
        api.patients.get(id),
        api.predictions.history(id)
      ])
      setPatient(patRes)
      setHistory(histRes)
    } catch (err) {
      console.error(err)
      // Mock Data
      setPatient({
        patient_id: id, first_name: 'John', last_name: 'Kamau', date_of_birth: '1995-05-12',
        gender: 'M', phone: '+254700000000', county: 'Nairobi', marital_status: 'single',
        number_of_partners_12m: 4, condom_use_frequency: 0.2, hiv_status: 'unknown'
      })
      setHistory([
        { id: 1, created_at: '2024-03-20T10:00:00Z', risk_level: 'high', risk_score: 0.72 },
        { id: 2, created_at: '2023-10-15T09:30:00Z', risk_level: 'moderate', risk_score: 0.45 },
      ])
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="p-8 text-center">Loading...</div>
  if (!patient) return <div className="p-8 text-center text-red-500">Patient not found</div>

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <button onClick={() => navigate('/patients')} className="flex items-center gap-2 text-muted hover:text-primary transition-colors text-sm">
        <ArrowLeft className="w-4 h-4" /> Back to Patients
      </button>

      <div className="flex flex-col md:flex-row justify-between md:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-primary flex items-center gap-3">
            <User className="w-6 h-6 text-accent" />
            {patient.first_name} {patient.last_name}
          </h1>
          <p className="text-muted mt-1 font-mono text-sm">{patient.patient_id}</p>
        </div>
        <button onClick={() => navigate('/assess')} className="btn-primary">
          <Activity className="w-4 h-4" /> Run New Prediction
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="card p-6">
            <h3 className="text-lg font-semibold mb-4">Demographics</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-y-4 gap-x-6 text-sm">
              <div><p className="text-muted mb-1">Gender</p><p className="font-medium text-primary">{patient.gender}</p></div>
              <div><p className="text-muted mb-1">Date of Birth</p><p className="font-medium text-primary">{patient.date_of_birth}</p></div>
              <div><p className="text-muted mb-1">Phone</p><p className="font-medium text-primary">{patient.phone || '—'}</p></div>
              <div><p className="text-muted mb-1">County</p><p className="font-medium text-primary">{patient.county || '—'}</p></div>
              <div><p className="text-muted mb-1">Marital Status</p><p className="font-medium text-primary capitalize">{patient.marital_status}</p></div>
            </div>
          </div>

          <div className="card p-6">
            <h3 className="text-lg font-semibold mb-4">Risk Factors Profile</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-y-4 gap-x-6 text-sm">
              <div><p className="text-muted mb-1">Partners (12m)</p><p className="font-medium text-primary">{patient.number_of_partners_12m}</p></div>
              <div><p className="text-muted mb-1">Condom Use</p><p className="font-medium text-primary">{(patient.condom_use_frequency * 100).toFixed(0)}%</p></div>
              <div><p className="text-muted mb-1">HIV Status</p><p className="font-medium text-primary capitalize">{patient.hiv_status}</p></div>
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Clock className="w-5 h-5 text-accent" /> Prediction History
            </h3>
            {history.length > 0 ? (
              <div className="space-y-4">
                {history.map((pred) => (
                  <div key={pred.id} className="p-3 border border-border rounded-xl flex justify-between items-center hover:bg-gray-50">
                    <div>
                      <p className="text-sm font-medium">{formatDate(pred.created_at)}</p>
                      <p className="text-xs text-muted capitalize mt-0.5">{pred.risk_level} Risk</p>
                    </div>
                    <div className="text-right">
                      <span className={`badge ${pred.risk_level === 'high' ? 'badge-red' : pred.risk_level === 'moderate' ? 'badge-orange' : 'badge-green'}`}>
                        {(pred.risk_score * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted text-center py-4">No predictions found.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}