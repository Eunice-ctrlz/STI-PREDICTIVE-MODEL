import { useState } from 'react'
import { Brain, CheckCircle2, FlaskConical, Info, Loader2, Terminal } from 'lucide-react'
import { api } from '../lib/api'
import { useApi } from '../hooks/useData'
import { AsyncBoundary, EmptyState, Skeleton } from '../components/States'
import { formatDate, formatNumber, humanize } from '../lib/utils'

const STATUS_BADGE = {
  deployed: 'badge-green',
  ready: 'badge-blue',
  training: 'badge-yellow',
  deprecated: 'badge-gray',
  failed: 'badge-red',
}

const STATUS_TONE = {
  deployed: 'bg-emerald-50 text-emerald-600',
  ready: 'bg-blue-50 text-blue-600',
  training: 'bg-amber-50 text-amber-600',
  deprecated: 'bg-gray-100 text-gray-500',
  failed: 'bg-red-50 text-red-600',
}

export default function MLModels() {
  const { data, loading, error, refetch } = useApi(() => api.ml.models(), [])
  const { data: jobs } = useApi(() => api.ml.jobs(), [])
  const [deployingId, setDeployingId] = useState(null)
  const [actionError, setActionError] = useState('')

  const models = data || []

  const handleDeploy = async (model) => {
    setDeployingId(model.id)
    setActionError('')
    try {
      await api.ml.deploy(model.id)
      await refetch()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setDeployingId(null)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title flex items-center gap-2">
          <Brain className="h-6 w-6 text-accent" />
          ML Models
        </h1>
        <p className="page-subtitle">Model registry, metrics and deployment</p>
      </div>

      {actionError && (
        <div className="card-flat border-red-200 bg-red-50/60 p-4 text-sm text-red-700">
          {actionError}
        </div>
      )}

      <AsyncBoundary
        loading={loading}
        error={error}
        onRetry={refetch}
        errorTitle="Could not load the model registry"
        loadingFallback={
          <div className="space-y-4">
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="card space-y-3 p-6">
                <Skeleton className="h-5 w-48" />
                <Skeleton className="h-4 w-72" />
                <Skeleton className="h-4 w-56" />
              </div>
            ))}
          </div>
        }
        isEmpty={models.length === 0}
        emptyFallback={
          <div className="card">
            <EmptyState
              icon={Brain}
              title="No models registered"
              description="Train a model, or register the artifacts already on disk, to populate this registry."
              action={
                <div className="space-y-2 text-left">
                  <CommandHint command="python manage.py train_sti_model" label="Train a new model" />
                  <CommandHint command="python manage.py sync_model_registry" label="Register existing artifacts" />
                </div>
              }
            />
          </div>
        }
      >
        <div className="grid gap-4">
          {models.map((model) => (
            <ModelCard
              key={model.id}
              model={model}
              deploying={deployingId === model.id}
              onDeploy={() => handleDeploy(model)}
            />
          ))}
        </div>
      </AsyncBoundary>

      {jobs?.length > 0 && (
        <section className="card p-6">
          <h3 className="section-title mb-4">Recent Training Jobs</h3>
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr className="border-b border-border">
                  <th className="th">Job</th>
                  <th className="th">Status</th>
                  <th className="th">Started</th>
                  <th className="th">Completed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {jobs.map((job) => (
                  <tr key={job.id} className="tr-hover">
                    <td className="td font-medium text-primary">#{job.id}</td>
                    <td className="td">
                      <span className={`badge ${STATUS_BADGE[job.status] || 'badge-gray'}`}>
                        {humanize(job.status)}
                      </span>
                    </td>
                    <td className="td text-muted">{formatDate(job.started_at)}</td>
                    <td className="td text-muted">{formatDate(job.completed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <div className="card-flat border-blue-100 bg-blue-50/50 p-6">
        <div className="flex items-start gap-3">
          <Info className="mt-0.5 h-5 w-5 shrink-0 text-blue-600" />
          <div>
            <h3 className="text-sm font-semibold text-primary">About this registry</h3>
            <p className="mt-1 text-xs leading-relaxed text-muted">
              Metrics shown here are read from each model's <code className="font-mono">metadata.json</code>,
              written at training time — they are not hand-entered. Deploying a model makes it the default
              used for live predictions. Re-running training updates the registry entry automatically.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function ModelCard({ model, deploying, onDeploy }) {
  const tone = STATUS_TONE[model.status] || STATUS_TONE.ready
  // metadata.json's data_source lands in `description`; flag synthetic training
  // data prominently so nobody mistakes these metrics for clinical validation.
  const isSynthetic = /synthetic/i.test(model.description || '')

  return (
    <div className="card p-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
        <div className="flex min-w-0 items-start gap-4">
          <div className={`shrink-0 rounded-xl p-3 ${tone}`}>
            <Brain className="h-6 w-6" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold text-primary">{model.name}</h3>
              {model.is_default && <span className="badge badge-green">Default</span>}
              <span className={`badge ${STATUS_BADGE[model.status] || 'badge-gray'}`}>
                {humanize(model.status)}
              </span>
            </div>
            <p className="mt-1 text-sm text-muted">
              v{model.version} · {humanize(model.model_type)}
              {model.training_completed_at && ` · trained ${formatDate(model.training_completed_at)}`}
              {model.training_data_size && ` · ${formatNumber(model.training_data_size)} samples`}
            </p>

            <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
              <Metric label="AUC-ROC" value={model.test_auc_roc} />
              <Metric label="F1" value={model.test_f1} />
              <Metric label="Accuracy" value={model.validation_accuracy} />
            </div>

            {isSynthetic && (
              <p className="mt-3 flex items-start gap-1.5 text-xs text-amber-700">
                <FlaskConical className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Trained on synthetic data — not clinically validated.
              </p>
            )}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {model.status === 'ready' && (
            <button onClick={onDeploy} disabled={deploying} className="btn-primary px-4 py-2 text-sm">
              {deploying ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              {deploying ? 'Deploying…' : 'Deploy'}
            </button>
          )}
          {model.status === 'deployed' && (
            <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-600">
              <CheckCircle2 className="h-4 w-4" />
              Serving predictions
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

function Metric({ label, value }) {
  const hasValue = value !== null && value !== undefined
  return (
    <span className="text-xs text-muted">
      {label}:{' '}
      <span className={`font-semibold ${hasValue ? 'text-primary' : 'text-gray-400'}`}>
        {hasValue ? Number(value).toFixed(4) : 'not recorded'}
      </span>
    </span>
  )
}

function CommandHint({ command, label }) {
  return (
    <div>
      <p className="mb-1 text-xs text-muted">{label}</p>
      <code className="flex items-center gap-2 rounded-lg bg-primary px-3 py-2 font-mono text-xs text-gray-200">
        <Terminal className="h-3.5 w-3.5 shrink-0 text-accent" />
        {command}
      </code>
    </div>
  )
}
