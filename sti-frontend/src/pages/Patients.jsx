import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Users, Search, Filter, Plus, FileText, Activity, X } from 'lucide-react'
import { api } from '../lib/api'
import { useApi, useDebounced } from '../hooks/useData'
import { AsyncBoundary, EmptyState, SkeletonTable } from '../components/States'
import { formatDate, formatGender } from '../lib/utils'

export default function Patients() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  // Seeded from the URL so the header search box can deep-link into this page.
  const [searchTerm, setSearchTerm] = useState(searchParams.get('search') || '')
  const [countyFilter, setCountyFilter] = useState(searchParams.get('county') || '')
  const debouncedSearch = useDebounced(searchTerm)

  useEffect(() => {
    const next = {}
    if (debouncedSearch) next.search = debouncedSearch
    if (countyFilter) next.county = countyFilter
    setSearchParams(next, { replace: true })
  }, [debouncedSearch, countyFilter, setSearchParams])

  // Search runs on the server so it matches every patient, not just the page
  // that happens to be loaded.
  const { data, loading, error, refetch } = useApi(
    () => api.patients.list({ search: debouncedSearch, county: countyFilter, limit: 100 }),
    [debouncedSearch, countyFilter]
  )

  const patients = useMemo(() => data || [], [data])
  const isFiltered = Boolean(debouncedSearch || countyFilter)

  // Build the county list from the data itself rather than a hardcoded trio.
  const { data: countySummary } = useApi(() => api.geospatial.countySummary(), [])
  const countyOptions = useMemo(() => {
    const fromSummary = (countySummary || []).map((c) => c.county).filter(Boolean)
    const fromPatients = patients.map((p) => p.county).filter(Boolean)
    return [...new Set([...fromSummary, ...fromPatients])].sort()
  }, [countySummary, patients])

  const clearFilters = () => {
    setSearchTerm('')
    setCountyFilter('')
  }

  return (
    <div className="space-y-6">
      <div className="page-header">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <Users className="h-6 w-6 text-accent" />
            Patient Directory
          </h1>
          <p className="page-subtitle">Manage patient records and screening histories</p>
        </div>
        <button onClick={() => navigate('/assess')} className="btn-primary">
          <Plus className="h-4 w-4" />
          New Patient
        </button>
      </div>

      <div className="card flex flex-wrap items-center gap-3 p-4">
        <div className="relative min-w-[240px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input
            type="search"
            placeholder="Search by ID, name or phone…"
            className="input-field pl-10"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            aria-label="Search patients"
          />
        </div>
        <div className="relative">
          <Filter className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <select
            className="input-field w-44 pl-10"
            value={countyFilter}
            onChange={(e) => setCountyFilter(e.target.value)}
            aria-label="Filter by county"
          >
            <option value="">All Counties</option>
            {countyOptions.map((county) => (
              <option key={county} value={county}>{county}</option>
            ))}
          </select>
        </div>
        {isFiltered && (
          <button onClick={clearFilters} className="btn-ghost text-sm">
            <X className="h-4 w-4" />
            Clear
          </button>
        )}
        {!loading && !error && (
          <span className="ml-auto text-xs text-muted">
            {patients.length} {patients.length === 1 ? 'patient' : 'patients'}
          </span>
        )}
      </div>

      <div className="card overflow-hidden">
        <AsyncBoundary
          loading={loading}
          error={error}
          onRetry={refetch}
          errorTitle="Could not load patients"
          loadingFallback={<SkeletonTable rows={6} cols={6} />}
          isEmpty={patients.length === 0}
          emptyFallback={
            isFiltered ? (
              <EmptyState
                icon={Search}
                title="No matching patients"
                description="No records match your search or county filter."
                action={<button onClick={clearFilters} className="btn-outline">Clear filters</button>}
              />
            ) : (
              <EmptyState
                icon={Users}
                title="No patients registered yet"
                description="Register your first patient by starting a risk assessment."
                action={
                  <button onClick={() => navigate('/assess')} className="btn-primary">
                    <Plus className="h-4 w-4" />
                    New Patient
                  </button>
                }
              />
            )
          }
        >
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr className="border-b border-border bg-gray-50/60">
                  <th className="th">Patient ID</th>
                  <th className="th">Name</th>
                  <th className="th">Age</th>
                  <th className="th">Gender</th>
                  <th className="th">County</th>
                  <th className="th">Registered</th>
                  <th className="th text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {patients.map((patient) => (
                  <tr key={patient.patient_id} className="tr-hover">
                    <td className="td">
                      <button
                        onClick={() => navigate(`/patients/${patient.patient_id}`)}
                        className="font-mono text-xs font-medium text-accent hover:underline"
                      >
                        {patient.patient_id}
                      </button>
                    </td>
                    <td className="td font-medium text-primary">{patient.full_name}</td>
                    <td className="td text-muted">{patient.age ?? '—'}</td>
                    <td className="td text-muted">{formatGender(patient.gender)}</td>
                    <td className="td text-muted">{patient.county || '—'}</td>
                    <td className="td text-muted">{formatDate(patient.created_at)}</td>
                    <td className="td">
                      <div className="flex justify-end gap-1">
                        <button
                          onClick={() => navigate(`/patients/${patient.patient_id}`)}
                          className="rounded-md p-1.5 text-muted transition-colors hover:bg-accent/10 hover:text-accent"
                          title="View details"
                        >
                          <FileText className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => navigate(`/assess?patient=${encodeURIComponent(patient.patient_id)}`)}
                          className="rounded-md p-1.5 text-muted transition-colors hover:bg-accent/10 hover:text-accent"
                          title="New prediction"
                        >
                          <Activity className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
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
