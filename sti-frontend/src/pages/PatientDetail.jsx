import { useNavigate, useParams } from 'react-router-dom'
import { Activity, ArrowLeft, Clock, MapPin, ShieldCheck, User } from 'lucide-react'
import { api } from '../lib/api'
import { useApi } from '../hooks/useData'
import { AsyncBoundary, EmptyState, ErrorState, LoadingState } from '../components/States'
import { formatDate, formatDateTime, formatGender, getRiskConfig, humanize } from '../lib/utils'

export default function PatientDetail() {
  const { id } = useParams()
  const navigate = useNavigate()

  const { data: patient, loading, error, refetch } = useApi(() => api.patients.get(id), [id])
  const {
    data: history,
    loading: historyLoading,
    error: historyError,
    refetch: refetchHistory,
  } = useApi(() => api.predictions.history(id), [id])

  if (loading) return <LoadingState label="Loading patient…" />
  if (error) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <BackButton onClick={() => navigate('/patients')} />
        <ErrorState error={error} onRetry={refetch} title={`Could not load patient ${id}`} />
      </div>
    )
  }
  if (!patient) return null

  const predictions = history || []
  const latest = predictions[0]

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <BackButton onClick={() => navigate('/patients')} />

      <div className="page-header">
        <div>
          <h1 className="flex items-center gap-3 text-2xl font-bold tracking-tight text-primary">
            <User className="h-6 w-6 text-accent" />
            {patient.first_name} {patient.last_name}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
            <span className="font-mono text-xs">{patient.patient_id}</span>
            {patient.age !== undefined && <span>· {patient.age} yrs</span>}
            <span>· {formatGender(patient.gender)}</span>
            {patient.county && (
              <span className="flex items-center gap-1">
                · <MapPin className="h-3 w-3" /> {patient.county}
              </span>
            )}
            {patient.is_active === false && <span className="badge badge-gray">Inactive</span>}
          </div>
        </div>
        <button
          onClick={() => navigate(`/assess?patient=${encodeURIComponent(patient.patient_id)}`)}
          className="btn-primary"
        >
          <Activity className="h-4 w-4" />
          Run New Prediction
        </button>
      </div>

      {latest && <LatestRiskBanner prediction={latest} />}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <section className="card p-6">
            <h3 className="mb-5 text-base font-semibold text-primary">Demographics</h3>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm md:grid-cols-3">
              <Field label="Gender" value={formatGender(patient.gender)} />
              <Field label="Date of Birth" value={formatDate(patient.date_of_birth)} />
              <Field label="Age" value={patient.age !== undefined ? `${patient.age}` : '—'} />
              <Field label="Phone" value={patient.phone} />
              <Field label="Email" value={patient.email} />
              <Field label="Marital Status" value={humanize(patient.marital_status)} />
              <Field label="County" value={patient.county} />
              <Field label="Sub-County" value={patient.sub_county} />
              <Field label="Ward" value={patient.ward} />
            </dl>
          </section>

          <section className="card p-6">
            <h3 className="mb-5 text-base font-semibold text-primary">Risk Factor Profile</h3>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm md:grid-cols-3">
              <Field label="Partners (12m)" value={patient.number_of_partners_12m} />
              <Field label="Partners (lifetime)" value={patient.number_of_partners_lifetime} />
              <Field
                label="Condom Use"
                value={
                  patient.condom_use_frequency !== null && patient.condom_use_frequency !== undefined
                    ? `${(patient.condom_use_frequency * 100).toFixed(0)}%`
                    : '—'
                }
              />
              <Field label="HIV Status" value={humanize(patient.hiv_status)} />
              <Field label="Prior STI History" value={yesNo(patient.prior_sti_history)} />
              <Field label="Substance Use" value={yesNo(patient.substance_use)} />
              <Field label="Symptoms Present" value={yesNo(patient.symptoms_present)} />
            </dl>
            {patient.symptom_description && (
              <div className="mt-5 rounded-xl border border-border bg-gray-50 p-4">
                <p className="label mb-1">Symptom notes</p>
                <p className="text-sm text-primary">{patient.symptom_description}</p>
              </div>
            )}
          </section>
        </div>

        <section className="card h-fit p-6">
          <h3 className="mb-5 flex items-center gap-2 text-base font-semibold text-primary">
            <Clock className="h-5 w-5 text-accent" />
            Prediction History
          </h3>
          <AsyncBoundary
            loading={historyLoading}
            error={historyError}
            onRetry={refetchHistory}
            errorTitle="Could not load history"
            loadingFallback={<LoadingState label="Loading history…" className="h-40" />}
            isEmpty={predictions.length === 0}
            emptyFallback={
              <EmptyState
                icon={Activity}
                title="No predictions yet"
                description="Run an assessment to generate this patient's first risk score."
                className="py-8"
              />
            }
          >
            <ol className="space-y-3">
              {predictions.map((pred) => {
                const cfg = getRiskConfig(pred.risk_level)
                return (
                  <li key={pred.id}>
                    <button
                      onClick={() => navigate(`/assess/result/${pred.id}`)}
                      className="flex w-full items-center justify-between rounded-xl border border-border p-3 text-left transition-colors hover:border-accent/40 hover:bg-gray-50"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-primary">
                          {formatDateTime(pred.created_at)}
                        </p>
                        <p className="mt-0.5 text-xs text-muted">{cfg.label}</p>
                      </div>
                      <span className={`badge ${cfg.badge} shrink-0`}>
                        {(pred.risk_score * 100).toFixed(0)}%
                      </span>
                    </button>
                  </li>
                )
              })}
            </ol>
          </AsyncBoundary>
        </section>
      </div>
    </div>
  )
}

function LatestRiskBanner({ prediction }) {
  const cfg = getRiskConfig(prediction.risk_level)
  return (
    <div className={`card-flat ${cfg.bg} ${cfg.border} p-5`}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <ShieldCheck className={`h-5 w-5 ${cfg.text}`} />
          <div>
            <p className={`text-sm font-semibold ${cfg.text}`}>Latest assessment: {cfg.label}</p>
            <p className="mt-0.5 text-xs text-muted">
              {formatDateTime(prediction.created_at)} · model {prediction.model_version}
            </p>
          </div>
        </div>
        <p className={`text-2xl font-bold ${cfg.text}`}>
          {(prediction.risk_score * 100).toFixed(1)}%
        </p>
      </div>
    </div>
  )
}

function BackButton({ onClick }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 text-sm text-muted transition-colors hover:text-primary"
    >
      <ArrowLeft className="h-4 w-4" /> Back to Patients
    </button>
  )
}

function Field({ label, value }) {
  const display =
    value === null || value === undefined || value === '' ? '—' : String(value)
  return (
    <div>
      <dt className="mb-1 text-muted">{label}</dt>
      <dd className="font-medium text-primary">{display}</dd>
    </div>
  )
}

function yesNo(value) {
  if (value === null || value === undefined) return '—'
  return value ? 'Yes' : 'No'
}
