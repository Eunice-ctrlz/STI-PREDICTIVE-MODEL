import { useMemo, useState } from 'react'
import { Download, Filter, Search, Shield, X } from 'lucide-react'
import { api } from '../lib/api'
import { useApi, useDebounced } from '../hooks/useData'
import { AsyncBoundary, EmptyState, SkeletonTable } from '../components/States'
import { downloadCsv, formatDateTime, humanize } from '../lib/utils'

const ACTION_BADGE = {
  create: 'badge-green',
  read: 'badge-blue',
  update: 'badge-yellow',
  delete: 'badge-red',
  predict: 'badge-purple',
  export: 'badge-orange',
  login: 'badge-gray',
  logout: 'badge-gray',
}

const ACTIONS = ['create', 'read', 'update', 'delete', 'predict', 'export', 'login', 'logout']

const PERIODS = [
  { value: 1, label: 'Last 24 hours' },
  { value: 7, label: 'Last 7 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 90, label: 'Last 90 days' },
]

export default function AuditLogs() {
  const [search, setSearch] = useState('')
  const [action, setAction] = useState('')
  const [days, setDays] = useState(7)
  const debouncedSearch = useDebounced(search)

  // action/days are filtered by the API; the free-text search is applied
  // client-side because the endpoint has no search parameter.
  const { data, loading, error, refetch } = useApi(
    () => api.compliance.auditLogs({ action, days }),
    [action, days]
  )

  const logs = useMemo(() => {
    const all = data || []
    if (!debouncedSearch) return all
    const needle = debouncedSearch.toLowerCase()
    return all.filter((log) =>
      [log.user_name, log.description, log.resource_type, log.ip_address]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(needle))
    )
  }, [data, debouncedSearch])

  const isFiltered = Boolean(debouncedSearch || action)

  const handleExport = () => {
    downloadCsv(
      `audit-logs-${new Date().toISOString().slice(0, 10)}.csv`,
      logs.map((log) => ({
        timestamp: log.created_at,
        user: log.user_name,
        action: log.action,
        resource: log.resource_type,
        description: log.description,
        ip_address: log.ip_address,
      }))
    )
  }

  return (
    <div className="space-y-6">
      <div className="page-header">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <Shield className="h-6 w-6 text-accent" />
            Audit Logs
          </h1>
          <p className="page-subtitle">Every API action recorded for compliance review</p>
        </div>
        <button onClick={handleExport} disabled={logs.length === 0} className="btn-outline">
          <Download className="h-4 w-4" />
          Export CSV
        </button>
      </div>

      <div className="card flex flex-wrap items-center gap-3 p-4">
        <div className="relative min-w-[240px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input
            type="search"
            placeholder="Search user, description or IP…"
            className="input-field pl-10"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search audit logs"
          />
        </div>
        <div className="relative">
          <Filter className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <select
            className="input-field w-40 pl-10"
            value={action}
            onChange={(e) => setAction(e.target.value)}
            aria-label="Filter by action"
          >
            <option value="">All Actions</option>
            {ACTIONS.map((a) => (
              <option key={a} value={a}>{humanize(a)}</option>
            ))}
          </select>
        </div>
        <select
          className="input-field w-40"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          aria-label="Time range"
        >
          {PERIODS.map((p) => (
            <option key={p.value} value={p.value}>{p.label}</option>
          ))}
        </select>
        {isFiltered && (
          <button onClick={() => { setSearch(''); setAction('') }} className="btn-ghost text-sm">
            <X className="h-4 w-4" />
            Clear
          </button>
        )}
        {!loading && !error && (
          <span className="ml-auto text-xs text-muted">
            {logs.length} {logs.length === 1 ? 'entry' : 'entries'}
          </span>
        )}
      </div>

      <div className="card overflow-hidden">
        <AsyncBoundary
          loading={loading}
          error={error}
          onRetry={refetch}
          errorTitle="Could not load audit logs"
          loadingFallback={<SkeletonTable rows={6} cols={6} />}
          isEmpty={logs.length === 0}
          emptyFallback={
            <EmptyState
              icon={Shield}
              title={isFiltered ? 'No matching entries' : 'No activity in this period'}
              description={
                isFiltered
                  ? 'Try a different action filter or time range.'
                  : 'Audit entries are written automatically as the API is used. Try widening the time range.'
              }
            />
          }
        >
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr className="border-b border-border bg-gray-50/60">
                  <th className="th">Time</th>
                  <th className="th">User</th>
                  <th className="th">Action</th>
                  <th className="th">Resource</th>
                  <th className="th">Description</th>
                  <th className="th">IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {logs.map((log) => (
                  <tr key={log.id} className="tr-hover">
                    <td className="td whitespace-nowrap text-xs text-muted">
                      {formatDateTime(log.created_at)}
                    </td>
                    <td className="td font-medium text-primary">{log.user_name || 'Anonymous'}</td>
                    <td className="td">
                      <span className={`badge ${ACTION_BADGE[log.action] || 'badge-gray'}`}>
                        {log.action}
                      </span>
                    </td>
                    <td className="td text-muted">{log.resource_type}</td>
                    <td className="td max-w-md truncate font-mono text-xs text-primary" title={log.description}>
                      {log.description}
                    </td>
                    <td className="td font-mono text-xs text-muted">{log.ip_address || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AsyncBoundary>
      </div>
    </div>
  )
}
