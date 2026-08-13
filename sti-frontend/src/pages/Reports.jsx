import { useMemo, useState } from 'react'
import { Download, FileText } from 'lucide-react'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '../lib/api'
import { useApi } from '../hooks/useData'
import { AsyncBoundary, EmptyState, Skeleton } from '../components/States'
import {
  downloadCsv, formatAgeGroup, formatDate, formatGender, formatNumber, humanize,
} from '../lib/utils'

const PERIODS = [
  { value: 7, label: 'Weekly' },
  { value: 30, label: 'Monthly' },
  { value: 90, label: 'Quarterly' },
  { value: 365, label: 'Annual' },
]

const GENDER_COLORS = { M: '#0d9488', F: '#f59e0b', O: '#8b5cf6', U: '#64748b' }

const CHART_TOOLTIP = {
  contentStyle: {
    borderRadius: '12px',
    border: '1px solid #e2e8f0',
    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
    fontSize: '12px',
  },
}

export default function Reports() {
  const [days, setDays] = useState(30)

  const { data, loading, error, refetch } = useApi(() => api.reporting.dashboard({ days }), [days])
  const { data: templates } = useApi(() => api.reporting.templates(), [])
  const { data: generated } = useApi(() => api.reporting.reports(), [])

  const genderData = useMemo(
    () =>
      Object.entries(data?.gender_distribution || {})
        .filter(([, value]) => value > 0)
        .map(([key, value]) => ({
          name: formatGender(key),
          value,
          color: GENDER_COLORS[key] || '#94a3b8',
        })),
    [data]
  )

  const trendData = useMemo(
    () =>
      (data?.daily_trend || []).map((row) => ({
        date: formatDate(row.date),
        screenings: row.count,
        avgRisk: row.avg_risk ? Number((row.avg_risk * 100).toFixed(1)) : 0,
      })),
    [data]
  )

  const ageData = useMemo(
    () =>
      Object.entries(data?.age_distribution || {}).map(([key, value]) => ({
        name: formatAgeGroup(key),
        patients: value,
      })),
    [data]
  )

  const periodLabel = PERIODS.find((p) => p.value === days)?.label || `${days} days`
  const hasData = Boolean(data?.summary?.total_screenings || data?.summary?.total_patients)

  const handleExport = () => {
    if (!data) return
    const rows = (data.county_breakdown || []).map((c) => ({
      county: c.county || 'Unknown',
      patients: c.patients,
      avg_risk_score: c.avg_risk != null ? c.avg_risk.toFixed(4) : '',
      high_risk_predictions: c.high_risk,
    }))

    // Fall back to the headline summary if there's no county breakdown, so the
    // button always produces a file with real numbers in it.
    const payload = rows.length
      ? rows
      : [
          {
            period: data.period,
            total_patients: data.summary.total_patients,
            total_screenings: data.summary.total_screenings,
            high_risk_patients: data.summary.high_risk_patients,
            avg_risk_score: data.summary.avg_risk_score,
          },
        ]

    downloadCsv(`moh-report-${periodLabel.toLowerCase()}-${new Date().toISOString().slice(0, 10)}.csv`, payload)
  }

  return (
    <div className="space-y-6">
      <div className="page-header">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <FileText className="h-6 w-6 text-accent" />
            MOH Reports
          </h1>
          <p className="page-subtitle">Public health reporting for the Ministry of Health</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="input-field w-40"
            aria-label="Reporting period"
          >
            {PERIODS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
          <button onClick={handleExport} disabled={!hasData} className="btn-primary">
            <Download className="h-4 w-4" />
            Export CSV
          </button>
        </div>
      </div>

      <AsyncBoundary
        loading={loading}
        error={error}
        onRetry={refetch}
        errorTitle="Could not load reporting data"
        loadingFallback={
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="card space-y-4 p-6">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-64 w-full rounded-xl" />
              </div>
            ))}
          </div>
        }
      >
        {!hasData ? (
          <div className="card">
            <EmptyState
              icon={FileText}
              title="No data for this period"
              description="Reports are generated from recorded screenings. Try a longer period, or run some assessments first."
            />
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <SummaryTile label="Patients" value={formatNumber(data.summary.total_patients)} />
              <SummaryTile label="Screenings" value={formatNumber(data.summary.total_screenings)} />
              <SummaryTile label="High Risk" value={formatNumber(data.summary.high_risk_patients)} />
              <SummaryTile label="Avg Risk Score" value={data.summary.avg_risk_score?.toFixed(3)} />
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div className="card p-6">
                <h3 className="section-title mb-6">Screening Trend</h3>
                {trendData.length === 0 ? (
                  <EmptyState title="No screenings in this period" className="py-20" />
                ) : (
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={trendData} maxBarSize={56}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
                      <Tooltip {...CHART_TOOLTIP} />
                      <Legend wrapperStyle={{ fontSize: '12px' }} />
                      <Bar dataKey="screenings" name="Screenings" fill="#0d9488" radius={[6, 6, 0, 0]} isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>

              <div className="card p-6">
                <h3 className="section-title mb-6">Gender Distribution</h3>
                {genderData.length === 0 ? (
                  <EmptyState title="No patients recorded" className="py-20" />
                ) : (
                  <>
                    <ResponsiveContainer width="100%" height={260}>
                      <PieChart>
                        <Pie
                          data={genderData}
                          cx="50%"
                          cy="50%"
                          innerRadius={60}
                          outerRadius={90}
                          paddingAngle={4}
                          dataKey="value"
                          stroke="none"
                          isAnimationActive={false}
                        >
                          {genderData.map((entry) => (
                            <Cell key={entry.name} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip {...CHART_TOOLTIP} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="mt-2 flex flex-wrap justify-center gap-4">
                      {genderData.map((item) => (
                        <div key={item.name} className="flex items-center gap-1.5">
                          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                          <span className="text-xs text-muted">{item.name}</span>
                          <span className="text-xs font-semibold text-primary">{formatNumber(item.value)}</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="card p-6">
              <h3 className="section-title mb-6">Age Distribution</h3>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={ageData} barSize={40}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
                  <Tooltip {...CHART_TOOLTIP} cursor={{ fill: '#f8fafc' }} />
                  <Bar dataKey="patients" name="Patients" fill="#0d9488" radius={[6, 6, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </AsyncBoundary>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="card p-6">
          <h3 className="section-title mb-4">Report Templates</h3>
          {templates?.length ? (
            <div className="space-y-3">
              {templates.map((template) => (
                <div key={template.id} className="rounded-xl border border-border p-4">
                  <h4 className="text-sm font-semibold text-primary">{template.name}</h4>
                  {template.description && (
                    <p className="mt-1 text-xs text-muted">{template.description}</p>
                  )}
                  {template.report_type && (
                    <span className="badge badge-gray mt-2">{humanize(template.report_type)}</span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              icon={FileText}
              title="No templates configured"
              description="Report templates are managed in the Django admin under MOH Reporting."
              className="py-10"
            />
          )}
        </section>

        <section className="card p-6">
          <h3 className="section-title mb-4">Generated Reports</h3>
          {generated?.length ? (
            <div className="overflow-x-auto">
              <table className="table-base">
                <thead>
                  <tr className="border-b border-border">
                    <th className="th">Report</th>
                    <th className="th">Status</th>
                    <th className="th">Generated</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {generated.map((report) => (
                    <tr key={report.id} className="tr-hover">
                      <td className="td font-medium text-primary">{report.title || `Report #${report.id}`}</td>
                      <td className="td">
                        <span className="badge badge-blue">{humanize(report.status)}</span>
                      </td>
                      <td className="td text-muted">{formatDate(report.generated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              icon={FileText}
              title="No reports generated"
              description="Use Export CSV above to produce a report from the current period's data."
              className="py-10"
            />
          )}
        </section>
      </div>
    </div>
  )
}

function SummaryTile({ label, value }) {
  return (
    <div className="stat-card">
      <p className="text-xs font-semibold uppercase tracking-wider text-muted">{label}</p>
      <p className="mt-2 text-2xl font-bold text-primary">{value ?? '—'}</p>
    </div>
  )
}
