import { useCallback, useEffect, useState } from 'react'
import {
  BookOpen, Info, ListChecks, RefreshCw, Sparkles,
} from 'lucide-react'
import { api } from '../lib/api'
import { Spinner } from './States'

/**
 * AI-generated explanation of an existing ML prediction.
 *
 * Deliberately does NOT use ErrorState. A failure here means one optional
 * layer is unavailable, not that the page failed -- the prediction rendered
 * above this component is complete and valid either way. So every failure
 * renders as a muted informational notice, never a red error block.
 *
 * All content produced by this component is explicitly labelled as
 * AI-generated so it is never mistaken for the model's clinical output.
 */

const UNAVAILABLE_MESSAGE =
  'The AI explanation service is temporarily unavailable. Your prediction result is still available.'

export default function AIExplanation({ predictionId }) {
  const [explanation, setExplanation] = useState(null)
  const [loading, setLoading] = useState(true)
  const [unavailable, setUnavailable] = useState('')

  const load = useCallback(
    async ({ refresh = false } = {}) => {
      setLoading(true)
      setUnavailable('')
      try {
        const result = await api.ai.explainPrediction(predictionId, { refresh })
        setExplanation(result)
      } catch (err) {
        // The backend returns 503 with a friendly message when the AI layer
        // is down or unconfigured; a network failure produces a different
        // message. Either way the user sees the same reassuring copy.
        setUnavailable(err?.message || UNAVAILABLE_MESSAGE)
        setExplanation(null)
      } finally {
        setLoading(false)
      }
    },
    [predictionId]
  )

  useEffect(() => {
    load()
  }, [load])

  return (
    <section className="card border-l-4 border-l-purple-500 p-6">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 section-title">
          <Sparkles className="h-4 w-4 text-purple-500" />
          AI Explanation
          <span className="badge badge-purple ml-1">AI-generated</span>
        </h3>

        {!loading && (
          <button
            onClick={() => load({ refresh: true })}
            className="flex items-center gap-1.5 text-xs text-muted transition-colors hover:text-accent print:hidden"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Regenerate
          </button>
        )}
      </div>

      <p className="mb-5 text-xs text-muted">
        Written by a language model to explain the result above in plain language. It does not
        produce, change or review the risk score.
      </p>

      {loading && (
        <div className="flex items-center gap-3 py-6 text-muted">
          <Spinner className="h-5 w-5 text-purple-500" />
          <p className="text-sm">Generating explanation…</p>
        </div>
      )}

      {!loading && unavailable && (
        <div className="card-flat bg-gray-50/80 p-4">
          <div className="flex items-start gap-3">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-muted">{unavailable}</p>
              <button
                onClick={() => load()}
                className="mt-3 inline-flex items-center gap-2 rounded-lg border border-border bg-white px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:border-accent/50 hover:text-accent print:hidden"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Try again
              </button>
            </div>
          </div>
        </div>
      )}

      {!loading && !unavailable && explanation && (
        <div className="space-y-6">
          <p className="text-sm leading-relaxed text-primary">{explanation.summary}</p>

          <Block icon={BookOpen} title="What this means">
            <p className="text-sm leading-relaxed text-primary">
              {explanation.what_this_means}
            </p>
          </Block>

          {explanation.important_considerations?.length > 0 && (
            <Block icon={Info} title="Important considerations">
              <BulletList items={explanation.important_considerations} dotClass="bg-amber-400" />
            </Block>
          )}

          {explanation.recommended_next_steps?.length > 0 && (
            <Block icon={ListChecks} title="Suggested next steps">
              <BulletList items={explanation.recommended_next_steps} dotClass="bg-accent" />
            </Block>
          )}

          <div className="card-flat border-amber-200 bg-amber-50/60 p-4">
            <div className="flex items-start gap-3">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <p className="text-xs leading-relaxed text-amber-900">
                <strong>Disclaimer.</strong> {explanation.disclaimer}
              </p>
            </div>
          </div>

          {explanation.generated_by && (
            <p className="text-xs text-muted">
              Generated by {explanation.generated_by.provider} ({explanation.generated_by.model})
              {explanation.cached && ' · saved from an earlier request'}
            </p>
          )}
        </div>
      )}
    </section>
  )
}

function Block({ icon: Icon, title, children }) {
  return (
    <div>
      <h4 className="mb-2.5 flex items-center gap-2 text-sm font-semibold text-primary">
        <Icon className="h-4 w-4 text-muted" />
        {title}
      </h4>
      {children}
    </div>
  )
}

function BulletList({ items, dotClass }) {
  return (
    <ul className="space-y-2.5">
      {items.map((item, index) => (
        <li key={index} className="flex items-start gap-2.5">
          <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${dotClass}`} />
          <span className="text-sm leading-relaxed text-primary">{item}</span>
        </li>
      ))}
    </ul>
  )
}
