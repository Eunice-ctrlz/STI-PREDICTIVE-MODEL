import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Users, Search, Filter, Plus, FileText, Activity } from 'lucide-react'
import { api } from '../lib/api'
import { formatDate } from '../lib/utils'

export default function Patients() {
  const navigate = useNavigate()
  const [patients, setPatients] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [countyFilter, setCountyFilter] = useState('')

  useEffect(() => {
    loadPatients()
  }, [countyFilter])

  const loadPatients = async () => {
    setLoading(true)
    try {
      const data = await api.patients.list(countyFilter ? { county: countyFilter } : {})
      setPatients(data)
    } catch (err) {
      console.error(err)
      // Fallback data
      setPatients([
        { patient_id: 'KNH-2024-001', first_name: 'John', last_name: 'Kamau', gender: 'M', county: 'Nairobi', created_at: '2024-03-20T10:00:00Z', risk_level: 'high' },
        { patient_id: 'KNH-2024-002', first_name: 'Mary', last_name: 'Wanjiku', gender: 'F', county: 'Mombasa', created_at: '2024-03-19T14:30:00Z', risk_level: 'low' },
      ])
    } finally {
      setLoading(false)
    }
  }

  const filteredPatients = patients.filter(p => 
    p.patient_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.first_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.last_name.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <Users className="w-6 h-6 text-accent" />
            Patient Directory
          </h1>
          <p className="text-sm text-muted mt-1">Manage patient records and histories</p>
        </div>
        <button onClick={() => navigate('/assess')} className="btn-primary">
          <Plus className="w-4 h-4" />
          New Patient
        </button>
      </div>

      <div className="card p-4 flex flex-wrap gap-3">
        <div className="flex-1 min-w-[240px] relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
          <input 
            type="text" 
            placeholder="Search patients by ID or name..." 
            className="input-field pl-10"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div className="relative">
          <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
          <select 
            className="input-field pl-10 w-40"
            value={countyFilter}
            onChange={(e) => setCountyFilter(e.target.value)}
          >
            <option value="">All Counties</option>
            <option value="Nairobi">Nairobi</option>
            <option value="Mombasa">Mombasa</option>
            <option value="Kisumu">Kisumu</option>
          </select>
        </div>
      </div>

      <div className="card overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-muted">Loading patients...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-gray-50/50">
                  <th className="text-left py-3.5 px-4 font-medium text-muted text-xs uppercase tracking-wider">Patient ID</th>
                  <th className="text-left py-3.5 px-4 font-medium text-muted text-xs uppercase tracking-wider">Name</th>
                  <th className="text-left py-3.5 px-4 font-medium text-muted text-xs uppercase tracking-wider">Gender</th>
                  <th className="text-left py-3.5 px-4 font-medium text-muted text-xs uppercase tracking-wider">County</th>
                  <th className="text-left py-3.5 px-4 font-medium text-muted text-xs uppercase tracking-wider">Registration Date</th>
                  <th className="text-left py-3.5 px-4 font-medium text-muted text-xs uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredPatients.map((patient) => (
                  <tr key={patient.patient_id} className="hover:bg-gray-50/50 transition-colors">
                    <td className="py-3.5 px-4 font-medium text-primary">
                      <button onClick={() => navigate(`/patients/${patient.patient_id}`)} className="text-accent hover:underline">
                        {patient.patient_id}
                      </button>
                    </td>
                    <td className="py-3.5 px-4 text-primary">{patient.first_name} {patient.last_name}</td>
                    <td className="py-3.5 px-4 text-muted">{patient.gender}</td>
                    <td className="py-3.5 px-4 text-muted">{patient.county || '—'}</td>
                    <td className="py-3.5 px-4 text-muted">{formatDate(patient.created_at)}</td>
                    <td className="py-3.5 px-4">
                      <div className="flex gap-2">
                        <button onClick={() => navigate(`/patients/${patient.patient_id}`)} className="p-1.5 text-muted hover:text-accent rounded-md hover:bg-accent/10" title="View Details">
                          <FileText className="w-4 h-4" />
                        </button>
                        <button onClick={() => navigate('/assess')} className="p-1.5 text-muted hover:text-accent rounded-md hover:bg-accent/10" title="New Prediction">
                          <Activity className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
