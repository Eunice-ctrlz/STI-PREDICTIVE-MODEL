import { useState } from 'react'
import { FileText, Download, BarChart3, TrendingUp } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'

export default function Reports() {
  const [period, setPeriod] = useState('monthly')
  
  const genderData = [
    { name: 'Male', value: 5234, color: '#0d9488' },
    { name: 'Female', value: 3087, color: '#f59e0b' },
    { name: 'Other', value: 129, color: '#64748b' },
  ]
  
  const monthlyData = [
    { month: 'Jan', screenings: 420, positive: 89 },
    { month: 'Feb', screenings: 380, positive: 76 },
    { month: 'Mar', screenings: 510, positive: 112 },
    { month: 'Apr', screenings: 490, positive: 98 },
    { month: 'May', screenings: 620, positive: 145 },
    { month: 'Jun', screenings: 580, positive: 132 },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <FileText className="w-6 h-6 text-accent" />
            MOH Reports
          </h1>
          <p className="text-sm text-muted mt-1">Generate and export public health reports</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={period} onChange={(e) => setPeriod(e.target.value)} className="input-field w-40">
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
            <option value="quarterly">Quarterly</option>
          </select>
          <button className="btn-primary">
            <Download className="w-4 h-4" />
            Export
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-6">
          <h3 className="text-sm font-semibold text-primary mb-6">Screening Trend</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={monthlyData}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }} />
              <Bar dataKey="screenings" fill="#0d9488" radius={[6, 6, 0, 0]} />
              <Bar dataKey="positive" fill="#ef4444" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-6">
          <h3 className="text-sm font-semibold text-primary mb-6">Gender Distribution</h3>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={genderData} cx="50%" cy="50%" innerRadius={60} outerRadius={90} paddingAngle={4} dataKey="value" stroke="none">
                {genderData.map((entry, index) => <Cell key={index} fill={entry.color} />)}
              </Pie>
              <Tooltip contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-4 mt-2">
            {genderData.map((item) => (
              <div key={item.name} className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                <span className="text-xs text-muted">{item.name}</span>
                <span className="text-xs font-semibold text-primary">{item.value.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card p-6">
        <h3 className="text-sm font-semibold text-primary mb-4">Report Templates</h3>
        <div className="grid md:grid-cols-3 gap-4">
          {[
            { title: 'Weekly Summary', desc: 'Screenings, risk distribution, and county breakdown', type: 'Auto-generated' },
            { title: 'Monthly Report', desc: 'Comprehensive epidemiological analysis for MOH', type: 'MOH Standard' },
            { title: 'Outbreak Alert', desc: 'Automated detection of unusual risk patterns', type: 'Trigger-based' },
          ].map((template) => (
            <div key={template.title} className="p-4 border border-border rounded-xl hover:border-accent/50 transition-colors">
              <h4 className="font-semibold text-primary text-sm">{template.title}</h4>
              <p className="text-xs text-muted mt-1 mb-3">{template.desc}</p>
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 text-gray-600">
                {template.type}
              </span>
              <button className="mt-3 w-full py-2 text-xs font-medium text-accent border border-accent/20 rounded-lg hover:bg-accent/5 transition-colors">
                Generate
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}