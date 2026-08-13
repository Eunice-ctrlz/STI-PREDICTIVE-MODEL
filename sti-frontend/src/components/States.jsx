import { AlertTriangle, Inbox, RefreshCw } from 'lucide-react'

/**
 * Shared loading / error / empty states.
 *
 * These exist so pages never quietly substitute invented data when a request
 * fails. In a clinical tool, showing a plausible-looking number that isn't real
 * is worse than showing nothing, so a failed fetch always surfaces as an error.
 */

export function Spinner({ className = 'h-5 w-5' }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={`inline-block animate-spin rounded-full border-2 border-current border-r-transparent ${className}`}
    />
  )
}

export function LoadingState({ label = 'Loading…', className = 'h-72' }) {
  return (
    <div className={`flex items-center justify-center ${className}`}>
      <div className="flex flex-col items-center gap-3 text-muted">
        <Spinner className="h-7 w-7 text-accent" />
        <p className="text-sm">{label}</p>
      </div>
    </div>
  )
}

/** Skeleton block sized by Tailwind classes, e.g. <Skeleton className="h-4 w-32" /> */
export function Skeleton({ className = 'h-4 w-full' }) {
  return <div className={`skeleton ${className}`} />
}

export function SkeletonCard() {
  return (
    <div className="stat-card">
      <div className="flex items-start justify-between">
        <div className="space-y-3">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-7 w-20" />
        </div>
        <Skeleton className="h-10 w-10 rounded-xl" />
      </div>
      <Skeleton className="mt-4 h-3 w-32" />
    </div>
  )
}

export function SkeletonTable({ rows = 5, cols = 5 }) {
  return (
    <div className="p-4 space-y-3">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className={`h-4 ${c === 0 ? 'w-40' : 'flex-1'}`} />
          ))}
        </div>
      ))}
    </div>
  )
}

export function ErrorState({ error, onRetry, title = 'Could not load this data' }) {
  return (
    <div className="card-flat border-red-200 bg-red-50/60 p-6">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-red-800">{title}</h3>
          <p className="mt-1 break-words text-sm text-red-700">
            {typeof error === 'string' ? error : error?.message || 'Unexpected error.'}
          </p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-3 inline-flex items-center gap-2 rounded-lg border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-100"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Try again
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export function EmptyState({
  icon: Icon = Inbox,
  title = 'Nothing here yet',
  description,
  action,
  className = 'py-14',
}) {
  return (
    <div className={`flex flex-col items-center justify-center px-6 text-center ${className}`}>
      <div className="mb-4 rounded-2xl bg-gray-100 p-3.5">
        <Icon className="h-6 w-6 text-gray-400" />
      </div>
      <h3 className="text-sm font-semibold text-primary">{title}</h3>
      {description && <p className="mt-1.5 max-w-sm text-sm text-muted">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

/**
 * Renders the right state for an async resource, or the children once data
 * has actually arrived. Keeps every page consistent and makes it impossible
 * to forget the error branch.
 */
export function AsyncBoundary({
  loading,
  error,
  onRetry,
  isEmpty = false,
  loadingFallback,
  emptyFallback,
  errorTitle,
  children,
}) {
  if (loading) return loadingFallback ?? <LoadingState />
  if (error) return <ErrorState error={error} onRetry={onRetry} title={errorTitle} />
  if (isEmpty) return emptyFallback ?? <EmptyState />
  return children
}
