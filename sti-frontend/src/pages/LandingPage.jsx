import { useNavigate } from 'react-router-dom'
import {
  Activity, ArrowRight, BarChart3, Brain, CheckCircle,
  Lock, Map, ShieldCheck,
} from 'lucide-react'
import { api } from '../lib/api'
import { useApi } from '../hooks/useData'
import { formatNumber } from '../lib/utils'

export default function LandingPage() {
  const navigate = useNavigate()

  // Headline figures come from the live API. If the backend is unreachable
  // these render as "—" rather than inventing impressive-looking numbers.
  const { data: metrics } = useApi(() => api.reporting.dashboard({ days: 365 }), [])
  const { data: counties } = useApi(() => api.geospatial.countySummary(), [])
  const { data: models } = useApi(() => api.ml.models(), [])

  const activeModel = (models || []).find((m) => m.is_default) || (models || [])[0]
  const summary = metrics?.summary

  const stat = (value, format = formatNumber) =>
    value === null || value === undefined ? '—' : format(value)

  return (
    <div className="min-h-screen bg-white">
      <nav className="fixed left-0 right-0 top-0 z-50 border-b border-gray-100 bg-white/80 backdrop-blur-md">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
                <ShieldCheck className="h-4 w-4 text-white" />
              </div>
              <span className="font-bold text-primary">STI Predictor</span>
            </div>
            <div className="hidden items-center gap-6 md:flex">
              <a href="#features" className="text-sm text-muted transition-colors hover:text-primary">Features</a>
              <a href="#how-it-works" className="text-sm text-muted transition-colors hover:text-primary">How it Works</a>
              <a href="#impact" className="text-sm text-muted transition-colors hover:text-primary">Impact</a>
              <button onClick={() => navigate('/dashboard')} className="btn-primary px-4 py-2 text-sm">
                Open Dashboard
              </button>
            </div>
            <button
              onClick={() => navigate('/dashboard')}
              className="btn-primary px-4 py-2 text-sm md:hidden"
            >
              Dashboard
            </button>
          </div>
        </div>
      </nav>

      <section className="px-4 pb-20 pt-32 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="grid items-center gap-12 lg:grid-cols-2">
            <div className="space-y-8">
              <div className="inline-flex items-center gap-2 rounded-full bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent">
                <Activity className="h-3.5 w-3.5" />
                Clinical Intelligence Platform
              </div>
              <h1 className="text-4xl font-bold leading-tight text-primary sm:text-5xl lg:text-6xl">
                Predicting Health,<br />
                <span className="text-accent">Protecting Kenya</span>
              </h1>
              <p className="max-w-lg text-lg leading-relaxed text-muted">
                Machine-learning STI risk prediction for clinicians and public health officials.
                Screening, geospatial analytics and MOH reporting — all in one platform.
              </p>
              <div className="flex flex-wrap gap-4">
                <button onClick={() => navigate('/dashboard')} className="btn-primary px-6 py-3 text-base">
                  Start Screening <ArrowRight className="h-4 w-4" />
                </button>
                <button onClick={() => navigate('/assess')} className="btn-outline px-6 py-3 text-base">
                  Risk Assessment
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-6 text-sm text-muted">
                {['Full audit trail', 'Consent tracking', 'Self-hosted data'].map((claim) => (
                  <div key={claim} className="flex items-center gap-1.5">
                    <CheckCircle className="h-4 w-4 text-emerald-500" />
                    <span>{claim}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="relative">
              <div className="absolute -inset-4 rounded-3xl bg-gradient-to-br from-accent/10 to-primary/5 blur-2xl" />
              <div className="card relative space-y-4 p-6">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted">
                      Average risk score
                    </p>
                    <p className="text-3xl font-bold text-primary">
                      {summary?.avg_risk_score != null
                        ? `${(summary.avg_risk_score * 100).toFixed(1)}%`
                        : '—'}
                    </p>
                  </div>
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent/10">
                    <Activity className="h-6 w-6 text-accent" />
                  </div>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-gray-100">
                  <div
                    className="h-full rounded-full bg-accent transition-all duration-1000"
                    style={{ width: `${(summary?.avg_risk_score || 0) * 100}%` }}
                  />
                </div>
                <div className="grid grid-cols-3 gap-3 pt-2">
                  <MiniStat value={stat(summary?.total_screenings)} label="Screenings" />
                  <MiniStat value={stat(summary?.high_risk_patients)} label="High Risk" />
                  <MiniStat value={stat(counties?.length)} label="Counties" />
                </div>
                <p className="rounded-xl border border-border bg-gray-50 p-3 text-xs text-muted">
                  Live figures from this instance over the last 12 months.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="features" className="bg-gray-50/50 py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mb-16 text-center">
            <h2 className="mb-4 text-3xl font-bold text-primary">Platform Features</h2>
            <p className="mx-auto max-w-2xl text-muted">
              Everything clinicians and public health officials need for STI prevention and control.
            </p>
          </div>
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            <FeatureCard
              icon={Brain}
              title="AI Prediction"
              description={
                activeModel?.test_auc_roc
                  ? `A ${activeModel.model_type.replace(/_/g, ' ')} model scoring ${activeModel.test_auc_roc.toFixed(3)} AUC-ROC on held-out test data.`
                  : 'A machine-learning model scores each patient’s risk from their recorded risk factors.'
              }
              color="blue"
            />
            <FeatureCard
              icon={Map}
              title="Geospatial Analytics"
              description="Interactive risk maps aggregating predictions by county and sub-county."
              color="teal"
            />
            <FeatureCard
              icon={BarChart3}
              title="MOH Reporting"
              description="Exportable epidemiological summaries by period, county, age and gender."
              color="indigo"
            />
            <FeatureCard
              icon={Lock}
              title="Compliance"
              description="Automatic audit logging, patient consent records and data retention policies."
              color="emerald"
            />
          </div>
        </div>
      </section>

      <section id="how-it-works" className="py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mb-16 text-center">
            <h2 className="mb-4 text-3xl font-bold text-primary">How It Works</h2>
            <p className="mx-auto max-w-2xl text-muted">
              From patient intake to public health insight in four steps.
            </p>
          </div>
          <div className="grid gap-8 md:grid-cols-4">
            {[
              { step: '01', title: 'Patient Intake', desc: 'Enter patient demographics and risk factors through a guided form.' },
              { step: '02', title: 'Risk Assessment', desc: 'The model analyses those factors and returns a probability score.' },
              { step: '03', title: 'Clinical Decision', desc: 'Review recommended tests and actions, then record your review.' },
              { step: '04', title: 'Public Health', desc: 'Aggregated results feed the MOH dashboards and geospatial maps.' },
            ].map((item, i) => (
              <div key={item.step} className="relative">
                <div className="mb-4 text-5xl font-bold text-gray-100">{item.step}</div>
                <h3 className="mb-2 font-semibold text-primary">{item.title}</h3>
                <p className="text-sm leading-relaxed text-muted">{item.desc}</p>
                {i < 3 && (
                  <div className="absolute right-0 top-8 hidden h-px w-full bg-gradient-to-r from-border to-transparent md:block" />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="impact" className="bg-primary py-20 text-white">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mb-16 text-center">
            <h2 className="mb-4 text-3xl font-bold">Platform Activity</h2>
            <p className="mx-auto max-w-2xl text-gray-400">
              Live totals recorded by this deployment over the last 12 months.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-8 lg:grid-cols-4">
            <ImpactStat value={stat(summary?.total_screenings)} label="Screenings Recorded" />
            <ImpactStat value={stat(summary?.high_risk_patients)} label="High-Risk Identified" />
            <ImpactStat
              value={activeModel?.test_auc_roc ? activeModel.test_auc_roc.toFixed(3) : '—'}
              label="Model AUC-ROC"
            />
            <ImpactStat value={stat(counties?.length)} label="Counties With Data" />
          </div>
          {activeModel && /synthetic/i.test(activeModel.description || '') && (
            <p className="mx-auto mt-10 max-w-2xl text-center text-xs text-gray-400">
              The active model is currently trained on synthetic data and has not been clinically
              validated. Metrics describe held-out synthetic test performance only.
            </p>
          )}
        </div>
      </section>

      <section className="py-20">
        <div className="mx-auto max-w-4xl px-4 text-center sm:px-6 lg:px-8">
          <h2 className="mb-4 text-3xl font-bold text-primary">Ready to get started?</h2>
          <p className="mx-auto mb-8 max-w-lg text-muted">
            Open the platform to record a screening and generate your first risk prediction.
          </p>
          <button onClick={() => navigate('/dashboard')} className="btn-primary px-8 py-3 text-lg">
            Launch Platform <ArrowRight className="h-5 w-5" />
          </button>
        </div>
      </section>

      <footer className="border-t border-border py-8">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-4 sm:px-6 md:flex-row lg:px-8">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-primary">
              <ShieldCheck className="h-3 w-3 text-white" />
            </div>
            <span className="text-sm font-semibold text-primary">STI Predictor</span>
          </div>
          <p className="text-center text-xs text-muted">
            Clinical decision support for STI prevention. Not a substitute for clinical judgement.
          </p>
          <p className="text-xs text-muted">© 2026 STI Predictor</p>
        </div>
      </footer>
    </div>
  )
}

function MiniStat({ value, label }) {
  return (
    <div className="rounded-xl bg-gray-50 p-3 text-center">
      <p className="text-lg font-bold text-primary">{value}</p>
      <p className="text-[10px] text-muted">{label}</p>
    </div>
  )
}

function FeatureCard({ icon: Icon, title, description, color }) {
  const colors = {
    blue: 'bg-blue-50 text-blue-600',
    teal: 'bg-teal-50 text-teal-600',
    indigo: 'bg-indigo-50 text-indigo-600',
    emerald: 'bg-emerald-50 text-emerald-600',
  }
  return (
    <div className="card p-6">
      <div className={`mb-4 flex h-10 w-10 items-center justify-center rounded-xl ${colors[color]}`}>
        <Icon className="h-5 w-5" />
      </div>
      <h3 className="mb-2 font-semibold text-primary">{title}</h3>
      <p className="text-sm leading-relaxed text-muted">{description}</p>
    </div>
  )
}

function ImpactStat({ value, label }) {
  return (
    <div className="text-center">
      <p className="mb-2 text-4xl font-bold">{value}</p>
      <p className="text-sm text-gray-400">{label}</p>
    </div>
  )
}
