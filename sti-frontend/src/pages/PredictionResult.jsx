import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
    ArrowLeft, AlertTriangle, Shield, CheckCircle,
    FlaskConical, FileText, Activity, Printer, Download
} from 'lucide-react'
import { getRiskConfig } from '../lib/utils'
import { api } from '../lib/api'

export default function PredictionResult() {
    const { predictionId } = useParams()
    const navigate = useNavigate()
    const [result, setResult] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        setError('')

        api.predictions.get(predictionId)
            .then((data) => {
                if (!cancelled) {
                    setResult(data)
                    setLoading(false)
                }
            })
            .catch((err) => {
                if (!cancelled) {
                    setError(err.message || 'Failed to load prediction result')
                    setLoading(false)
                }
            })

        return () => { cancelled = true }
    }, [predictionId])

    if (loading) {
        return (
            <div className="flex items-center justify-center h-96">
                <div className="flex flex-col items-center gap-3">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent" />
                    <p className="text-sm text-muted">Analyzing risk factors...</p>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="max-w-3xl mx-auto">
                <button onClick={() => navigate('/assess')} className="flex items-center gap-2 text-muted hover:text-primary transition-colors text-sm mb-6">
                    <ArrowLeft className="w-4 h-4" />
                    Back to Assessment
                </button>
                <div className="card p-8 border-2 border-red-200 bg-red-50">
                    <p className="text-sm text-red-700">{error}</p>
                </div>
            </div>
        )
    }

    if (!result) return null

    const config = getRiskConfig(result.risk_level)
    const RiskIcon = config.icon === 'Shield' ? Shield : config.icon === 'AlertOctagon' ? AlertTriangle : AlertTriangle

    return (
        <div className="max-w-3xl mx-auto space-y-6">
            <button onClick={() => navigate('/assess')} className="flex items-center gap-2 text-muted hover:text-primary transition-colors text-sm">
                <ArrowLeft className="w-4 h-4" />
                Back to Assessment
            </button>

            {/* Risk Score Card */}
            <div className={`card p-8 border-2 ${config.border} ${config.bg}`}>
                <div className="flex items-start justify-between">
                    <div>
                        <div className="flex items-center gap-2 mb-2">
                            <RiskIcon className={`w-6 h-6 ${config.text}`} />
                            <span className={`text-sm font-semibold uppercase tracking-wider ${config.text}`}>{config.label}</span>
                        </div>
                        <h1 className="text-3xl font-bold text-primary">Risk Assessment Result</h1>
                        <p className="text-muted mt-1">{result.patient_name} <span className="font-mono text-xs">({result.patient_id})</span></p>
                    </div>
                    <div className="text-right">
                        <div className={`text-5xl font-bold ${config.text}`}>
                            {(result.risk_score * 100).toFixed(1)}<span className="text-2xl">%</span>
                        </div>
                        <p className="text-xs text-muted mt-1">Risk Probability</p>
                    </div>
                </div>

                {/* Score Bar */}
                <div className="mt-8">
                    <div className="h-3 bg-white/60 rounded-full overflow-hidden">
                        <div
                            className={`h-full rounded-full transition-all duration-1000 ${config.bar}`}
                            style={{ width: `${result.risk_score * 100}%` }}
                        />
                    </div>
                    <div className="flex justify-between text-xs text-muted mt-2">
                        <span>0%</span>
                        <span>25%</span>
                        <span>50%</span>
                        <span>75%</span>
                        <span>100%</span>
                    </div>
                </div>

                <div className="mt-6 p-4 bg-white rounded-xl border border-white/50">
                    <p className="text-sm text-primary font-medium">{config.message}</p>
                    {result.confidence_interval_lower != null && result.confidence_interval_upper != null && (
                        <p className="text-xs text-muted mt-1">
                            Confidence Interval: {(result.confidence_interval_lower * 100).toFixed(1)}% – {(result.confidence_interval_upper * 100).toFixed(1)}%
                        </p>
                    )}
                </div>
            </div>

            {/* Top Risk Factors */}
            <div className="card p-6">
                <h3 className="text-sm font-semibold text-primary mb-6 flex items-center gap-2">
                    <Activity className="w-4 h-4 text-accent" />
                    Top Risk Factors
                </h3>
                <div className="space-y-4">
                    {Object.entries(result.top_risk_factors || {}).map(([factor, importance]) => (
                        <div key={factor}>
                            <div className="flex justify-between text-sm mb-1.5">
                                <span className="capitalize text-primary">{factor.replace(/_/g, ' ')}</span>
                                <span className="font-semibold text-primary">{(importance * 100).toFixed(1)}%</span>
                            </div>
                            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-accent rounded-full transition-all duration-700"
                                    style={{ width: `${Math.min(importance * 300, 100)}%` }}
                                />
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Recommendations */}
            <div className="card p-6">
                <h3 className="text-sm font-semibold text-primary mb-4 flex items-center gap-2">
                    <FlaskConical className="w-4 h-4 text-accent" />
                    Recommended Tests
                </h3>
                <div className="flex flex-wrap gap-2 mb-6">
                    {(result.recommended_tests || []).map((test) => (
                        <span key={test} className="px-3 py-1.5 bg-accent/10 text-accent rounded-lg text-sm font-medium">
                            {test}
                        </span>
                    ))}
                </div>

                <h3 className="text-sm font-semibold text-primary mb-4 flex items-center gap-2">
                    <FileText className="w-4 h-4 text-accent" />
                    Recommended Actions
                </h3>
                <div className="bg-gray-50 rounded-xl p-4">
                    <p className="text-sm text-primary leading-relaxed">{result.recommended_actions}</p>
                </div>
            </div>

            {/* Actions */}
            <div className="flex flex-wrap gap-3">
                <button onClick={() => navigate('/patients')} className="btn-primary">
                    <CheckCircle className="w-4 h-4" />
                    Mark as Reviewed
                </button>
                <button onClick={() => window.print()} className="btn-ghost border border-border">
                    <Printer className="w-4 h-4" />
                    Print Report
                </button>
                <button className="btn-ghost border border-border">
                    <Download className="w-4 h-4" />
                    Export PDF
                </button>
            </div>

            <p className="text-xs text-muted text-center">
                Model: {result.model_name} ({result.model_version}) • Generated: {new Date(result.created_at).toLocaleString()}
            </p>
        </div>
    )
}