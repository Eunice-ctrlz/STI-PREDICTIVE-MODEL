import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  Activity, AlertTriangle, ArrowLeft, CheckCircle, FileText,
  FlaskConical, Info, Loader2, Printer, Shield, User,
} from 'lucide-react'
import { api } from '../lib/api'
import { useApi } from '../hooks/useData'
import { ErrorState, LoadingState } from '../components/States'
import { formatDateTime, getRiskConfig, humanize } from '../lib/utils'

export default function PredictionResult() {
  const { predictionId } = useParams()
  const navigate = useNavigate()

  const { data: result, loading, error, refetch, setData } = useApi(
    () => api.predictions.get(predictionId),
    [predictionId]
  )

  const [validating, setValidating] = useState(false)
  const [validateError, setValidateError] = useState('')

  const handleValidate = async () => {
    setValidating(true)
    setValidateError('')
    try {
      await api.predictions.validate(predictionId, { notes: 'Reviewed in clinical UI' })
      // Reflect the change locally so the button state updates immediately.
      setData((prev) => (prev ? { ...prev, validated_by_clinician: true } : prev))
    } catch (err) {
      setValidateError(err.message)
    } finally {
      setValidating(false)
    }
  }

  if (loading) return <LoadingState label="Loading prediction…" className="h-96" />

  if (error) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <BackLink onClick={() => navigate('/assess')} />
        <ErrorState error={error} onRetry={refetch} title="Could not load this prediction" />
      </div>
    )
  }

  if (!result) return null

  const config = getRiskConfig(result.risk_level)
  const RiskIcon = config.icon === 'Shield' ? Shield : AlertTriangle
  const factors = Object.entries(result.top_risk_factors || {})

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <BackLink onClick={() => navigate('/assess')} />
        <Link
          to={`/patients/${encodeURIComponent(result.patient_id)}`}
          className="flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-accent"
        >
          <User className="h-4 w-4" />
          View patient record
        </Link>
      </div>

      <section className={`card border-2 p-8 ${config.border} ${config.bg}`}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <RiskIcon className={`h-6 w-6 ${config.text}`} />
              <span className={`text-sm font-semibold uppercase tracking-wider ${config.text}`}>
                {config.label}
              </span>
              {result.validated_by_clinician && (
                <span className="badge badge-green">
                  <CheckCircle className="mr-1 h-3 w-3" />
                  Reviewed
                </span>
              )}
            </div>
            <h1 className="text-3xl font-bold tracking-tight text-primary">
              Risk Assessment Result
            </h1>
            <p className="mt-1 text-muted">
              {result.patient_name}{' '}
              <span className="font-mono text-xs">({result.patient_id})</span>
            </p>
          </div>
          <div className="text-right">
            <div className={`text-5xl font-bold ${config.text}`}>
              {(result.risk_score * 100).toFixed(1)}
              <span className="text-2xl">%</span>
            </div>
            <p className="mt-1 text-xs text-muted">Risk probability</p>
          </div>
        </div>

        <div className="mt-8">
          <div
            className="h-3 overflow-hidden rounded-full bg-white/60"
            role="meter"
            aria-valuenow={Number((result.risk_score * 100).toFixed(1))}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Risk score"
          >
            <div
              className={`h-full rounded-full transition-all duration-1000 ${config.bar}`}
              style={{ width: `${result.risk_score * 100}%` }}
            />
          </div>
          <div className="mt-2 flex justify-between text-xs text-muted">
            <span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span>
          </div>
        </div>

        <div className="mt-6 rounded-xl border border-white/60 bg-white p-4">
          <p className="text-sm font-medium text-primary">{config.message}</p>
          {result.confidence_interval_lower != null && result.confidence_interval_upper != null && (
            <p className="mt-1.5 text-xs text-muted">
              Confidence interval: {(result.confidence_interval_lower * 100).toFixed(1)}% –{' '}
              {(result.confidence_interval_upper * 100).toFixed(1)}%
            </p>
          )}
        </div>
      </section>

      {factors.length > 0 && (
        <section className="card p-6">
          <h3 className="mb-6 flex items-center gap-2 section-title">
            <Activity className="h-4 w-4 text-accent" />
            Top Contributing Factors
          </h3>
          <div className="space-y-4">
            {factors.map(([factor, importance]) => {
              const isNumeric = typeof importance === 'number'
              const pct = isNumeric ? Math.min(importance * 100, 100) : 0
              return (
                <div key={factor}>
                  <div className="mb-1.5 flex justify-between text-sm">
                    <span className="text-primary">{humanize(factor)}</span>
                    {isNumeric ? (
                      <span className="font-semibold text-primary">{pct.toFixed(1)}%</span>
                    ) : (
                      <span className="text-xs italic text-muted">{importance}</span>
                    )}
                  </div>
                  {isNumeric && (
                    <div className="h-2 overflow-hidden rounded-full bg-gray-100">
                      <div
                        className="h-full rounded-full bg-accent transition-all duration-700"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          <p className="mt-5 text-xs text-muted">
            Values are the model's relative feature importances for this patient — they show which
            inputs drove the score, not the probability of any individual infection.
          </p>
        </section>
      )}

      {result.likely_stis?.length > 0 && (
        <section className="card border-l-4 border-l-orange-500 p-6">
          <h3 className="mb-3 flex items-center gap-2 section-title">
            <AlertTriangle className="h-4 w-4 text-orange-500" />
            Most Likely STI Infections
          </h3>
          <p className="mb-4 text-xs text-muted">
            Based on the patient's symptoms, behaviour and demographics, these are the most likely
            specific STIs to screen for:
          </p>
          <div className="flex flex-wrap gap-2.5">
            {result.likely_stis.map((sti) => (
              <span
                key={sti}
                className="flex items-center gap-1.5 rounded-xl border border-orange-200 bg-orange-50 px-4 py-2 text-sm font-semibold text-orange-800"
              >
                <span className="h-2 w-2 rounded-full bg-orange-500" />
                {sti}
              </span>
            ))}
          </div>
        </section>
      )}

      <section className="card p-6">
        <h3 className="mb-4 flex items-center gap-2 section-title">
          <FlaskConical className="h-4 w-4 text-accent" />
          Recommended Tests
        </h3>
        <div className="mb-6 flex flex-wrap gap-2">
          {(result.recommended_tests || []).map((test) => (
            <span key={test} className="rounded-lg bg-accent/10 px-3 py-1.5 text-sm font-medium text-accent">
              {test}
            </span>
          ))}
        </div>

        <h3 className="mb-4 flex items-center gap-2 section-title">
          <FileText className="h-4 w-4 text-accent" />
          Recommended Actions
        </h3>
        <div className="rounded-xl bg-gray-50 p-4">
          <p className="text-sm leading-relaxed text-primary">{result.recommended_actions}</p>
        </div>
      </section>

      {validateError && (
        <div className="card-flat border-red-200 bg-red-50/60 p-4 text-sm text-red-700">
          {validateError}
        </div>
      )}

      <div className="flex flex-wrap gap-3 print:hidden">
        <button
          onClick={handleValidate}
          disabled={validating || result.validated_by_clinician}
          className="btn-primary"
        >
          {validating ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
          {result.validated_by_clinician ? 'Reviewed' : validating ? 'Saving…' : 'Mark as Reviewed'}
        </button>
        <button onClick={() => window.print()} className="btn-outline">
          <Printer className="h-4 w-4" />
          Print Report
        </button>
      </div>

      <div className="card-flat border-amber-200 bg-amber-50/60 p-4">
        <div className="flex items-start gap-3">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
          <p className="text-xs leading-relaxed text-amber-900">
            <strong>Decision support only.</strong> This score is generated by{' '}
            {result.model_name} ({result.model_version}) and must not replace clinical judgement or
            laboratory diagnosis. Check the model's training data and validation metrics on the{' '}
            <Link to="/models" className="font-medium underline">ML Models</Link> page before relying
            on it in practice.
          </p>
        </div>
      </div>

      <p className="text-center text-xs text-muted">
        Generated {formatDateTime(result.created_at)}
      </p>
    </div>
  )
}

function BackLink({ onClick }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 text-sm text-muted transition-colors hover:text-primary"
    >
      <ArrowLeft className="h-4 w-4" />
      Back to Assessment
    </button>
  )
}
