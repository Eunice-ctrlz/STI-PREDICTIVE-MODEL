import { useState } from 'react'
import { Shield, Search, Filter } from 'lucide-react'

const ACTION_COLORS = {
  create: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  read: 'bg-blue-50 text-blue-700 border-blue-200',
  update: 'bg-amber-50 text-amber-700 border-amber-200',
  delete: 'bg-red-50 text-red-700 border-red-200',
  predict: 'bg-purple-50 text-purple-700 border-purple-200',
  export: 'bg-orange-50 text-orange-700 border-orange-200',
}

export default function AuditLogs() {
  const [logs] = useState([
    { id: 1, user_name: 'Dr. Kamau', action: 'predict', resource_type: 'Prediction', description: 'Risk prediction for KNH-2024-001', ip_address: '192.168.1.45', created_at: '2024-03-20T10:30:00Z' },
    { id: 2, user_name: 'Dr. Wanjiku', action: 'create', resource_type: 'Patient', description: 'Created patient KNH-2024-006', ip_address: '192.168.1.46', created_at: '2024-03-20T09:15:00Z' },
    { id: 3, user_name: 'Admin', action: 'export', resource_type: 'Report', description: 'Exported monthly MOH report', ip_address: '192.168.1.10', created_at: '2024-03-20T08:00:00Z' },
    { id: 4, user_name: 'Dr. Kamau', action: 'read', resource_type: 'Patient', description: 'Viewed patient KNH-2024-003', ip_address: '192.168.1.45', created_at: '2024-03-19T16:45:00Z' },
    { id: 5, user_name: 'Dr. Ochieng', action: 'update', resource_type: 'Patient', description: 'Updated risk factors for KNH-2024-002', ip_address: '192.168.1.47', created_at: '2024-03-19T14:20:00Z' },
  ])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title flex items-center gap-2">
          <Shield className="w-6 h-6 text-accent" />
          Audit Logs
        </h1>
        <p className="text-sm text-muted mt-1">Track all system actions for compliance</p>
      </div>

      <div className="card p-4 flex flex-wrap gap-3">
        <div className="flex-1 min-w-[240px] relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
          <input type="text" placeholder="Search logs..." className="input-field pl-10" />
        </div>
        <div className="relative">
          <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
          <select className="input-field pl-10 w-36">
            <option value="">All Actions</option>
            <option value="create">Create</option>
            <option value="read">Read</option>
            <option value="update">Update</option>
            <option value="predict">Predict</option>
            <option value="export">Export</option>
          </select>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-gray-50/50">
                <th className="text-left py-3.5 px-4 font-medium text-muted text-xs uppercase tracking-wider">Time</th>
                <th className="text-left py-3.5 px-4 font-medium text-muted text-xs uppercase tracking-wider">User</th>
                <th className="text-left py-3.5 px-4 font-medium text-muted text-xs uppercase tracking-wider">Action</th>
                <th className="text-left py-3.5 px-4 font-medium text-muted text-xs uppercase tracking-wider">Resource</th>
                <th className="text-left py-3.5 px-4 font-medium text-muted text-xs uppercase tracking-wider">Description</th>
                <th className="text-left py-3.5 px-4 font-medium text-muted text-xs uppercase tracking-wider">IP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {logs.map((log) => (
                <tr key={log.id} className="hover:bg-gray-50/50 transition-colors">
                  <td className="py-3.5 px-4 text-xs text-muted">
                    {new Date(log.created_at).toLocaleString()}
                  </td>
                  <td className="py-3.5 px-4 font-medium text-primary">{log.user_name}</td>
                  <td className="py-3.5 px-4">
                    <span className={`badge ${ACTION_COLORS[log.action] || 'bg-gray-100 text-gray-600'}`}>
                      {log.action}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 text-muted">{log.resource_type}</td>
                  <td className="py-3.5 px-4 text-primary max-w-xs truncate">{log.description}</td>
                  <td className="py-3.5 px-4 text-xs font-mono text-muted">{log.ip_address}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}