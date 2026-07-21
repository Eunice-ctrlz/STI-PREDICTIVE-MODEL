import { useState } from 'react'
import { Brain, CheckCircle, Clock, AlertCircle, ArrowUpRight, GitBranch } from 'lucide-react'

export default function MLModels() {
  const [models] = useState([
    { id: 1, name: 'sti_risk_v1', version: '1.0.0', type: 'Random Forest', status: 'deployed', auc: 0.89, f1: 0.85, accuracy: 0.87, isDefault: true, trained: '2024-01-15' },
    { id: 2, name: 'sti_risk_v2', version: '2.0.0-beta', type: 'XGBoost', status: 'ready', auc: 0.92, f1: 0.88, accuracy: 0.90, isDefault: false, trained: '2024-03-20' },
    { id: 3, name: 'sti_hiv_v1', version: '1.0.0', type: 'Neural Network', status: 'training', auc: 0.00, f1: 0.00, accuracy: 0.00, isDefault: false, trained: '—' },
  ])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title flex items-center gap-2">
          <Brain className="w-6 h-6 text-accent" />
          ML Models
        </h1>
        <p className="text-sm text-muted mt-1">Model registry, training jobs, and deployment</p>
      </div>

      <div className="grid gap-4">
        {models.map((model) => (
          <div key={model.id} className="card p-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className={`p-3 rounded-xl ${model.status === 'deployed' ? 'bg-emerald-50 text-emerald-600' : model.status === 'training' ? 'bg-amber-50 text-amber-600' : 'bg-blue-50 text-blue-600'}`}>
                <Brain className="w-6 h-6" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-primary">{model.name}</h3>
                  {model.isDefault && (
                    <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 text-xs rounded-full font-medium border border-emerald-200">
                      Default
                    </span>
                  )}
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${
                    model.status === 'deployed' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
                    model.status === 'training' ? 'bg-amber-50 text-amber-700 border-amber-200' :
                    'bg-blue-50 text-blue-700 border-blue-200'
                  }`}>
                    {model.status === 'deployed' ? 'Deployed' : model.status === 'training' ? 'Training' : 'Ready'}
                  </span>
                </div>
                <p className="text-sm text-muted">v{model.version} • {model.type} • Trained: {model.trained}</p>
                {model.status !== 'training' && (
                  <div className="flex gap-4 mt-2 text-xs">
                    <span className="text-muted">AUC: <span className="font-semibold text-primary">{model.auc}</span></span>
                    <span className="text-muted">F1: <span className="font-semibold text-primary">{model.f1}</span></span>
                    <span className="text-muted">Acc: <span className="font-semibold text-primary">{model.accuracy}</span></span>
                  </div>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              {model.status === 'ready' && (
                <button className="btn-primary text-sm py-2 px-4">
                  Deploy
                </button>
              )}
              <button className="btn-ghost border border-border text-sm py-2 px-4">
                <GitBranch className="w-4 h-4" />
                Details
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="card p-6 bg-blue-50/50 border-blue-100">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-blue-600 mt-0.5" />
          <div>
            <h3 className="font-semibold text-primary text-sm">Model Registry</h3>
            <p className="text-xs text-muted mt-1 leading-relaxed">
              All models are versioned and tracked. Deployed models are used for live predictions. 
              Retrain models monthly with new data for best performance. Current default model achieves 89% AUC-ROC on the test set.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}