import React from 'react';
import type { Alert } from '../../services/clinicianApi';
import { getRiskColor } from '../../utils/riskColors';

interface Props {
  alerts: Alert[];
  onAction: (alertId: string, action: string) => void;
}

export const AlertQueue: React.FC<Props> = ({ alerts, onAction }) => {
  const getUrgencyBadge = (riskScore: number) => {
    if (riskScore > 0.9) return { text: 'EMERGENCY', class: 'bg-red-600 text-white' };
    if (riskScore > 0.7) return { text: 'CRITICAL', class: 'bg-red-500 text-white' };
    if (riskScore > 0.5) return { text: 'HIGH', class: 'bg-orange-500 text-white' };
    return { text: 'MODERATE', class: 'bg-yellow-500 text-white' };
  };

  return (
    <div className="space-y-4">
      {alerts.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-12 text-center">
          <div className="text-6xl mb-4">✅</div>
          <h3 className="text-xl font-semibold text-gray-900">No pending alerts</h3>
          <p className="text-gray-500">All patient risk alerts have been reviewed.</p>
        </div>
      ) : (
        alerts.map(alert => {
          const urgency = getUrgencyBadge(alert.risk_score);
          
          return (
            <div
              key={alert.alert_id}
              className="bg-white rounded-lg shadow border-l-4 hover:shadow-md transition"
              style={{ borderLeftColor: getRiskColor(alert.risk_level).replace('bg-', '') }}
            >
              <div className="p-6">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="flex items-center gap-3 mb-2">
                      <span className={`px-3 py-1 rounded-full text-xs font-bold ${urgency.class}`}>
                        {urgency.text}
                      </span>
                      <span className="text-sm text-gray-500">
                        {new Date(alert.triggered_at).toLocaleString()}
                      </span>
                    </div>
                    <h3 className="text-lg font-semibold">
                      Anonymous Patient {alert.anonymous_id.slice(0, 8)}...
                    </h3>
                    <p className="text-gray-600">
                      Risk Score: {(alert.risk_score * 100).toFixed(1)}%
                    </p>
                  </div>
                  <div className="text-right">
                    <div className="text-3xl font-bold text-gray-900">
                      {(alert.risk_score * 100).toFixed(0)}%
                    </div>
                    <div className="text-sm text-gray-500">Risk Score</div>
                  </div>
                </div>

                {/* Top Features */}
                <div className="mb-4">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">Top Contributing Factors:</h4>
                  <div className="flex flex-wrap gap-2">
                    {alert.top_features.map((feature: { feature: string; contribution: string; description: string }, i: number) => (
                      <span
                        key={i}
                        className="bg-gray-100 text-gray-700 px-3 py-1 rounded-full text-sm"
                      >
                        {feature.feature.replace('_', ' ')}
                      </span>
                    ))}
                  </div>
                </div>

                {/* STI Probabilities */}
                <div className="mb-4">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">STI Probabilities:</h4>
                  <div className="grid grid-cols-3 gap-3">
                    {Object.entries(alert.sti_probabilities)
                      .sort(([,a], [,b]) => (b as number) - (a as number))
                      .slice(0, 3)
                      .map(([sti, prob]) => (
                        <div key={sti} className="bg-gray-50 rounded-lg p-3">
                          <div className="text-xs text-gray-500 uppercase">{sti}</div>
                          <div className="text-lg font-bold">
                            {((prob as number) * 100).toFixed(0)}%
                          </div>
                        </div>
                      ))}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex gap-3">
                  <button
                    onClick={() => onAction(alert.alert_id, 'acknowledge')}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                  >
                    Acknowledge
                  </button>
                  <button
                    onClick={() => onAction(alert.alert_id, 'review')}
                    className="px-4 py-2 border border-blue-600 text-blue-600 rounded-lg hover:bg-blue-50"
                  >
                    Start Review
                  </button>
                  <button
                    onClick={() => onAction(alert.alert_id, 'escalate')}
                    className="px-4 py-2 border border-orange-600 text-orange-600 rounded-lg hover:bg-orange-50"
                  >
                    Escalate
                  </button>
                </div>
              </div>
            </div>
          );
        })
      )}
    </div>
  );
};