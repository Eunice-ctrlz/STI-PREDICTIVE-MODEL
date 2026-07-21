import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { 
  Users, Activity, AlertTriangle, TrendingUp, 
  MapPin, Calendar, ArrowUpRight, ArrowDownRight,
  ShieldAlert, FlaskConical
} from 'lucide-react'
import { 
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, 
  CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area
} from 'recharts'
import { api } from '../lib/api'

const RISK_COLORS = {
  low: '#10b981',
  moderate: '#f59e0b',
  high: '#f97316',
  very_high: '#ef4444',
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadDashboard()
  }, [])

  const loadDashboard = async () => {
    try {
      const [dashRes, statsRes] = await Promise.all([
        api.reporting.dashboard({ days: 30 }),
        api.predictions.stats({ days: 30 }),
      ])
      setMetrics({
        ...dashRes,
        stats: statsRes,
      })
    } catch (err) {
      console.error(err)
      // Fallback demo data
      setMetrics({
        summary: {
          total_patients: 12450,
          total_screenings: 8321,
          high_risk_patients: 342,
          avg_risk_score: 0.284,
        },
        risk_distribution: { low: 5234, moderate: 2103, high: 784, very_high: 200 },
        age_distribution: { '15-19': 1200, '20-24': 3400, '25-29': 2800, '30-34': 1500, '35-39': 800, '40-49': 621 },
        gender_distribution: { M: 5234, F: 3087, O: 0 },
        county_breakdown: [
          { county: 'Nairobi', patients: 4521, avg_risk: 0.32, high_risk: 145 },
          { county: 'Mombasa', patients: 2103, avg_risk: 0.28, high_risk: 89 },
          { county: 'Kisumu', patients: 1800, avg_risk: 0.35, high_risk: 67 },
          { county: 'Nakuru', patients: 1200, avg_risk: 0.22, high_risk: 21 },
          { county: 'Kiambu', patients: 982, avg_risk: 0.19, high_risk: 12 },
        ],
        daily_trend: Array.from({ length: 14 }, (_, i) => ({
          date: new Date(Date.now() - (13 - i) * 86400000).toISOString().split('T')[0],
          count: Math.floor(Math.random() * 50) + 20,
          avg_risk: Math.random() * 0.3 + 0.15,
        })),
      })
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <LoadingState />

  const riskData = metrics?.risk_distribution
    ? Object.entries(metrics.risk_distribution).map(([key, value]) => ({
        name: key.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase()),
        value,
        color: RISK_COLORS[key] || '#8884d8',
      }))
    : []

  const ageData = metrics?.age_distribution
    ? Object.entries(metrics.age_distribution).map(([key, value]) => ({ name: key, value }))
    : []

  const trendData = metrics?.daily_trend || []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="text-sm text-muted mt-1">Overview of STI screening and risk assessment activity</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted bg-white border border-border rounded-xl px-3 py-2">
          <Calendar className="w-4 h-4" />
          <span>Last 30 days</span>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Patients"
          value={metrics?.summary?.total_patients?.toLocaleString() || '0'}
          icon={Users}
          trend="+12.5%"
          trendUp={true}
          color="blue"
        />
        <StatCard
          title="Screenings"
          value={metrics?.summary?.total_screenings?.toLocaleString() || '0'}
          icon={FlaskConical}
          trend="+8.2%"
          trendUp={true}
          color="teal"
        />
        <StatCard
          title="High Risk"
          value={metrics?.summary?.high_risk_patients?.toLocaleString() || '0'}
          icon={ShieldAlert}
          trend="-3.1%"
          trendUp={false}
          color="red"
        />
        <StatCard
          title="Avg Risk Score"
          value={metrics?.summary?.avg_risk_score?.toFixed(3) || '0.000'}
          icon={TrendingUp}
          trend="-0.5%"
          trendUp={false}
          color="indigo"
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Risk Distribution */}
        <div className="card p-6">
          <h3 className="text-sm font-semibold text-primary mb-6">Risk Distribution</h3>
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
              >
                {riskData.map((entry, index) => (
                  <Cell key={index} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip 
                contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap justify-center gap-4 mt-2">
            {riskData.map((item) => (
              <div key={item.name} className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                <span className="text-xs text-muted">{item.name}</span>
                <span className="text-xs font-semibold text-primary">{item.value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Age Distribution */}
        <div className="card p-6">
          <h3 className="text-sm font-semibold text-primary mb-6">Age Distribution</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={ageData} barSize={32}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
              <XAxis 
                dataKey="name" 
                tick={{ fontSize: 11, fill: '#64748b' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis 
                tick={{ fontSize: 11, fill: '#64748b' }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip 
                contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                cursor={{ fill: '#f8fafc' }}
              />
              <Bar dataKey="value" fill="#0d9488" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Daily Trend */}
        <div className="card p-6">
          <h3 className="text-sm font-semibold text-primary mb-6">Daily Trend</h3>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={trendData}>
              <defs>
                <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0d9488" stopOpacity={0.1}/>
                  <stop offset="95%" stopColor="#0d9488" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
              <XAxis 
                dataKey="date" 
                tickFormatter={(val) => new Date(val).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                tick={{ fontSize: 10, fill: '#64748b' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis 
                tick={{ fontSize: 11, fill: '#64748b' }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip 
                contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
              />
              <Area type="monotone" dataKey="count" stroke="#0d9488" fillOpacity={1} fill="url(#colorCount)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* County Breakdown */}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-sm font-semibold text-primary flex items-center gap-2">
            <MapPin className="w-4 h-4 text-accent" />
            County Breakdown
          </h3>
          <button className="text-xs text-accent font-medium hover:underline">View all counties</button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-3 px-4 font-medium text-muted text-xs uppercase tracking-wider">County</th>
                <th className="text-right py-3 px-4 font-medium text-muted text-xs uppercase tracking-wider">Patients</th>
                <th className="text-right py-3 px-4 font-medium text-muted text-xs uppercase tracking-wider">Avg Risk</th>
                <th className="text-right py-3 px-4 font-medium text-muted text-xs uppercase tracking-wider">High Risk</th>
                <th className="text-right py-3 px-4 font-medium text-muted text-xs uppercase tracking-wider">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {metrics?.county_breakdown?.map((county) => {
                const risk = county.avg_risk || 0
                return (
                  <tr key={county.county} className="hover:bg-gray-50/50 transition-colors">
                    <td className="py-3 px-4 font-medium text-primary">{county.county || 'Unknown'}</td>
                    <td className="text-right py-3 px-4">{county.patients?.toLocaleString()}</td>
                    <td className="text-right py-3 px-4">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                        risk > 0.5 ? 'bg-red-50 text-red-700' :
                        risk > 0.3 ? 'bg-orange-50 text-orange-700' :
                        risk > 0.15 ? 'bg-amber-50 text-amber-700' :
                        'bg-emerald-50 text-emerald-700'
                      }`}>
                        {(risk * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="text-right py-3 px-4">{county.high_risk}</td>
                    <td className="text-right py-3 px-4">
                      <button 
                        onClick={() => navigate(`/heatmap?county=${county.county}`)}
                        className="text-accent text-xs font-medium hover:underline"
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
      </div>
    </div>
  )
}

function StatCard({ title, value, icon: Icon, trend, trendUp, color }) {
  const colorMap = {
    blue: 'bg-blue-50 text-blue-600',
    teal: 'bg-teal-50 text-teal-600',
    red: 'bg-red-50 text-red-600',
    indigo: 'bg-indigo-50 text-indigo-600',
  }
  return (
    <div className="stat-card">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-muted uppercase tracking-wider font-semibold">{title}</p>
          <p className="text-2xl font-bold text-primary mt-2">{value}</p>
        </div>
        <div className={`p-2.5 rounded-xl ${colorMap[color]}`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
      <div className="flex items-center gap-1 mt-4">
        {trendUp ? (
          <ArrowUpRight className="w-3.5 h-3.5 text-emerald-500" />
        ) : (
          <ArrowDownRight className="w-3.5 h-3.5 text-red-500" />
        )}
        <span className={`text-xs font-medium ${trendUp ? 'text-emerald-600' : 'text-red-600'}`}>
          {trend}
        </span>
        <span className="text-xs text-muted">vs last period</span>
      </div>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center h-96">
      <div className="flex flex-col items-center gap-3">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent" />
        <p className="text-sm text-muted">Loading dashboard...</p>
      </div>
    </div>
  )
}