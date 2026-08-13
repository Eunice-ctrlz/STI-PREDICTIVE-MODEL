import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Users, TrendingUp, MapPin, Calendar,
  ArrowUpRight, ArrowDownRight, Minus,
  ShieldAlert, FlaskConical, Activity,
} from 'lucide-react'
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area,
} from 'recharts'
import { api } from '../lib/api'
import { useApi } from '../hooks/useData'
import { AsyncBoundary, EmptyState, SkeletonCard, Skeleton } from '../components/States'
import { RISK_COLORS, formatAgeGroup, formatNumber, humanize } from '../lib/utils'

const PERIOD_OPTIONS = [
  { value: 7, label: 'Last 7 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 90, label: 'Last 90 days' },
  { value: 365, label: 'Last 12 months' },
]

const CHART_TOOLTIP = {
  contentStyle: {
    borderRadius: '12px',
    border: '1px solid #e2e8f0',
    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
    fontSize: '12px',
  },
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [days, setDays] = useState(30)

  const { data: metrics, loading, error, refetch } = useApi(
    () => api.reporting.dashboard({ days }),
    [days]
  )

  const summary = metrics?.summary
  const change = metrics?.change_pct || {}
  const hasActivity = Boolean(summary && (summary.total_patients || summary.total_screenings))

  const riskData = Object.entries(metrics?.risk_distribution || {})
    .map(([key, value]) => ({ name: humanize(key), value, color: RISK_COLORS[key] || '#94a3b8' }))
    .filter((d) => d.value > 0)

  const ageData = Object.entries(metrics?.age_distribution || {})
    .map(([key, value]) => ({ name: formatAgeGroup(key), value }))

  const trendData = metrics?.daily_trend || []
  const counties = metrics?.county_breakdown || []

  return (
    <div className="space-y-6">
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">Overview of STI screening and risk assessment activity</p>
        </div>
        <label className="flex items-center gap-2 rounded-xl border border-border bg-white px-3 py-2 text-sm text-muted">
          <Calendar className="h-4 w-4 shrink-0" />
          <span className="sr-only">Reporting period</span>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="cursor-pointer bg-transparent font-medium text-primary outline-none"
          >
            {PERIOD_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </label>
      </div>

      <AsyncBoundary
        loading={loading}
        error={error}
        onRetry={refetch}
        errorTitle="Could not load dashboard metrics"
        loadingFallback={<DashboardSkeleton />}
      >
        {!hasActivity ? (
          <div className="card">
            <EmptyState
              icon={Activity}
              title="No screening activity yet"
              description="Once you run a risk assessment, this dashboard will show live screening volumes, risk distribution and county breakdowns."
              action={
                <button onClick={() => navigate('/assess')} className="btn-primary">
                  Run first assessment
                </button>
              }
            />
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                title="Total Patients"
                value={formatNumber(summary.total_patients)}
                icon={Users}
                change={change.total_patients}
                color="blue"
              />
              <StatCard
                title="Screenings"
                value={formatNumber(summary.total_screenings)}
                icon={FlaskConical}
                change={change.total_screenings}
                color="teal"
              />
              <StatCard
                title="High Risk"
                value={formatNumber(summary.high_risk_patients)}
                icon={ShieldAlert}
                change={change.high_risk_patients}
                higherIsWorse
                color="red"
              />
              <StatCard
                title="Avg Risk Score"
                value={summary.avg_risk_score?.toFixed(3) ?? '0.000'}
                icon={TrendingUp}
                change={change.avg_risk_score}
                higherIsWorse
                color="indigo"
              />
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              <ChartCard title="Risk Distribution">
                {riskData.length === 0 ? (
                  <EmptyState title="No predictions in this period" className="py-16" />
                ) : (
                  <>
                    <ResponsiveContainer width="100%" height={240}>
                      <PieChart>
                        <Pie
                          data={riskData}
                          cx="50%"
                          cy="50%"
                          innerRadius={60}
                          outerRadius={90}
                          paddingAngle={4}
                          dataKey="value"
                          stroke="none"
                          isAnimationActive={false}
                        >
                          {riskData.map((entry) => (
                            <Cell key={entry.name} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip {...CHART_TOOLTIP} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-2">
                      {riskData.map((item) => (
                        <div key={item.name} className="flex items-center gap-1.5">
                          <span
                            className="h-2.5 w-2.5 rounded-full"
                            style={{ backgroundColor: item.color }}
                          />
                          <span className="text-xs text-muted">{item.name}</span>
                          <span className="text-xs font-semibold text-primary">{item.value}</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </ChartCard>

              <ChartCard title="Age Distribution">
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={ageData} barSize={32}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                    <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
                    <Tooltip {...CHART_TOOLTIP} cursor={{ fill: '#f8fafc' }} />
                    <Bar dataKey="value" name="Patients" fill="#0d9488" radius={[6, 6, 0, 0]} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="Daily Screening Trend">
                <ResponsiveContainer width="100%" height={280}>
                  <AreaChart data={trendData}>
                    <defs>
                      <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#0d9488" stopOpacity={0.25} />
                        <stop offset="95%" stopColor="#0d9488" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={(val) =>
                        new Date(val).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                      }
                      tick={{ fontSize: 10, fill: '#64748b' }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
                    <Tooltip {...CHART_TOOLTIP} />
                    <Area
                      type="monotone"
                      dataKey="count"
                      name="Screenings"
                      isAnimationActive={false}
                      stroke="#0d9488"
                      fill="url(#colorCount)"
                      strokeWidth={2}
                      // A single day of activity draws no line segment, so keep
                      // the point markers visible.
                      dot={{ r: 3, fill: '#0d9488', strokeWidth: 0 }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>

            <div className="card p-6">
              <div className="mb-6 flex items-center justify-between">
                <h3 className="section-title flex items-center gap-2">
                  <MapPin className="h-4 w-4 text-accent" />
                  County Breakdown
                </h3>
                <button
                  onClick={() => navigate('/heatmap')}
                  className="text-xs font-medium text-accent hover:underline"
                >
                  View risk map
                </button>
              </div>

              {counties.length === 0 ? (
                <EmptyState title="No county data" description="County figures appear once patients have a county recorded." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="table-base">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="th">County</th>
                        <th className="th text-right">Patients</th>
                        <th className="th text-right">Avg Risk</th>
                        <th className="th text-right">High Risk</th>
                        <th className="th text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {counties.map((county) => {
                        const risk = county.avg_risk || 0
                        return (
                          <tr key={county.county || 'unknown'} className="tr-hover">
                            <td className="td font-medium text-primary">{county.county || 'Unknown'}</td>
                            <td className="td text-right">{formatNumber(county.patients)}</td>
                            <td className="td text-right">
                              <span className={`badge ${riskBadge(risk)}`}>{(risk * 100).toFixed(1)}%</span>
                            </td>
                            <td className="td text-right">{county.high_risk}</td>
                            <td className="td text-right">
                              <button
                                onClick={() => navigate(`/heatmap?county=${encodeURIComponent(county.county || '')}`)}
                                className="text-xs font-medium text-accent hover:underline"
                              >
                                View Map
                              </button>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </AsyncBoundary>
    </div>
  )
}

function riskBadge(risk) {
  if (risk > 0.5) return 'badge-red'
  if (risk > 0.3) return 'badge-orange'
  if (risk > 0.15) return 'badge-yellow'
  return 'badge-green'
}

function ChartCard({ title, children }) {
  return (
    <div className="card p-6">
      <h3 className="section-title mb-6">{title}</h3>
      {children}
    </div>
  )
}

/**
 * `change` is a real period-over-period percentage from the API, or null when
 * there is no prior period to compare against — in which case no delta is shown
 * rather than an invented one.
 */
function StatCard({ title, value, icon: Icon, change, color, higherIsWorse = false }) {
  const colorMap = {
    blue: 'bg-blue-50 text-blue-600',
    teal: 'bg-teal-50 text-teal-600',
    red: 'bg-red-50 text-red-600',
    indigo: 'bg-indigo-50 text-indigo-600',
  }

  const hasChange = change !== null && change !== undefined
  const isUp = hasChange && change > 0
  const isFlat = hasChange && change === 0
  const isGood = higherIsWorse ? !isUp : isUp
  const TrendIcon = isFlat ? Minus : isUp ? ArrowUpRight : ArrowDownRight
  const tone = isFlat ? 'text-muted' : isGood ? 'text-emerald-600' : 'text-red-600'

  return (
    <div className="stat-card">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted">{title}</p>
          <p className="mt-2 text-2xl font-bold text-primary">{value}</p>
        </div>
        <div className={`rounded-xl p-2.5 ${colorMap[color]}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
      <div className="mt-4 flex items-center gap-1">
        {hasChange ? (
          <>
            <TrendIcon className={`h-3.5 w-3.5 ${tone}`} />
            <span className={`text-xs font-medium ${tone}`}>
              {change > 0 ? '+' : ''}{change}%
            </span>
            <span className="text-xs text-muted">vs previous period</span>
          </>
        ) : (
          <span className="text-xs text-muted">No prior period to compare</span>
        )}
      </div>
    </div>
  )
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="card space-y-4 p-6">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-56 w-full rounded-xl" />
          </div>
        ))}
      </div>
    </div>
  )
}
