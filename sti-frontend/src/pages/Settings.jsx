import { Brain, Database, Server, Settings as SettingsIcon, ShieldCheck } from 'lucide-react'
import { api } from '../lib/api'
import { useApi } from '../hooks/useData'
import { AsyncBoundary, EmptyState, Skeleton } from '../components/States'
import { formatDate, formatNumber, humanize } from '../lib/utils'

export default function Settings() {
  const { data: models, loading: modelsLoading, error: modelsError, refetch: refetchModels } =
    useApi(() => api.ml.models(), [])
  const { data: policies, loading: policiesLoading, error: policiesError, refetch: refetchPolicies } =
    useApi(() => api.compliance.retentionPolicies(), [])
  const { data: facilities } = useApi(() => api.clinicians.facilities(), [])

  const activeModel = (models || []).find((m) => m.is_default) || (models || [])[0]

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="page-title flex items-center gap-2">
          <SettingsIcon className="h-6 w-6 text-accent" />
          Settings
        </h1>
        <p className="page-subtitle">System configuration and platform status</p>
      </div>

      <section className="card p-6">
        <SectionHeader
          icon={Brain}
          title="Active Prediction Model"
          description="The model currently serving live risk predictions."
        />
        <AsyncBoundary
          loading={modelsLoading}
          error={modelsError}
          onRetry={refetchModels}
          errorTitle="Could not load model settings"
          loadingFallback={<Skeleton className="h-24 w-full rounded-xl" />}
          isEmpty={!activeModel}
          emptyFallback={
            <EmptyState
              icon={Brain}
              title="No model registered"
              description="Run python manage.py sync_model_registry to register the trained model."
              className="py-8"
            />
          }
        >
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm md:grid-cols-3">
            <Field label="Name" value={activeModel?.name} mono />
            <Field label="Version" value={activeModel?.version} mono />
            <Field label="Algorithm" value={humanize(activeModel?.model_type)} />
            <Field label="Status" value={humanize(activeModel?.status)} />
            <Field
              label="Trained"
              value={activeModel?.training_completed_at ? formatDate(activeModel.training_completed_at) : '—'}
            />
            <Field
              label="Training samples"
              value={activeModel?.training_data_size ? formatNumber(activeModel.training_data_size) : '—'}
            />
          </dl>
          {activeModel?.description && (
            <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
              <strong>Data source:</strong> {activeModel.description}
            </p>
          )}
        </AsyncBoundary>
      </section>

      <section className="card p-6">
        <SectionHeader
          icon={Database}
          title="Data Retention Policies"
          description="How long each category of data is kept before anonymisation or deletion."
        />
        <AsyncBoundary
          loading={policiesLoading}
          error={policiesError}
          onRetry={refetchPolicies}
          errorTitle="Could not load retention policies"
          loadingFallback={<Skeleton className="h-24 w-full rounded-xl" />}
          isEmpty={!policies?.length}
          emptyFallback={
            <EmptyState
              icon={Database}
              title="No retention policies configured"
              description="Add policies in the Django admin under Compliance › Data retention policies."
              className="py-8"
            />
          }
        >
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr className="border-b border-border">
                  <th className="th">Data Type</th>
                  <th className="th text-right">Retention</th>
                  <th className="th text-right">Anonymise After</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {(policies || []).map((policy) => (
                  <tr key={policy.id} className="tr-hover">
                    <td className="td font-medium text-primary">{humanize(policy.data_type)}</td>
                    <td className="td text-right text-muted">{policy.retention_days} days</td>
                    <td className="td text-right text-muted">
                      {policy.anonymize_after_days ? `${policy.anonymize_after_days} days` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AsyncBoundary>
      </section>

      <section className="card p-6">
        <SectionHeader
          icon={Server}
          title="Platform"
          description="Connection and deployment details for this instance."
        />
        <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm md:grid-cols-3">
          <Field label="API endpoint" value={import.meta.env.VITE_API_URL || '/api (proxied)'} mono />
          <Field label="Environment" value={import.meta.env.MODE} />
          <Field label="Registered facilities" value={facilities ? formatNumber(facilities.length) : '—'} />
        </dl>
      </section>

      <section className="card-flat border-blue-100 bg-blue-50/50 p-6">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-blue-600" />
          <div>
            <h3 className="text-sm font-semibold text-primary">User management</h3>
            <p className="mt-1 text-xs leading-relaxed text-muted">
              This build has no authentication layer — the API is open and audit entries are
              recorded as <span className="font-mono">Anonymous</span>. Accounts, roles and
              clinician records are currently managed through the Django admin at{' '}
              <span className="font-mono">/admin/</span>.
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}

function SectionHeader({ icon: Icon, title, description }) {
  return (
    <div className="mb-5">
      <h2 className="flex items-center gap-2 text-base font-semibold text-primary">
        <Icon className="h-5 w-5 text-accent" />
        {title}
      </h2>
      {description && <p className="mt-1 text-sm text-muted">{description}</p>}
    </div>
  )
}

function Field({ label, value, mono = false }) {
  const display = value === null || value === undefined || value === '' ? '—' : String(value)
  return (
    <div>
      <dt className="mb-1 text-muted">{label}</dt>
      <dd className={`font-medium text-primary ${mono ? 'font-mono text-xs' : ''}`}>{display}</dd>
    </div>
  )
}
