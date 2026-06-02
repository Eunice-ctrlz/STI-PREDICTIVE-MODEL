import React from 'react';
import type { AssessmentResult } from '../../services/patientApi';
import { getRiskColor, getRiskIcon } from '../../utils/riskColors';

interface Props {
  result: AssessmentResult;
  onFindClinics: () => void;
  onRetake: () => void;
}

export const RiskResult: React.FC<Props> = ({ result, onFindClinics, onRetake }) => {
  const riskColor = getRiskColor(result.overall_risk_level);
  const RiskIcon = getRiskIcon(result.overall_risk_level);

  return (
    <div className="max-w-2xl mx-auto">
      {/* Risk Level Card */}
      <div className={`rounded-lg p-8 mb-6 text-white ${riskColor}`}>
        <div className="flex items-center gap-4 mb-4">
          <RiskIcon className="w-12 h-12" />
          <div>
            <h2 className="text-3xl font-bold capitalize">
              {result.overall_risk_level} Risk
            </h2>
            <p className="text-lg opacity-90">
              Score: {(result.overall_risk_score * 100).toFixed(1)}%
            </p>
          </div>
        </div>
        
        {result.mandatory_clinical_review && (
          <div className="bg-white/20 rounded-lg p-4 mt-4">
            <p className="font-semibold flex items-center gap-2">
              <span className="text-2xl">⚠️</span>
              This assessment requires clinical review
            </p>
          </div>
        )}
      </div>

      {/* Explanation */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h3 className="text-xl font-bold mb-3">{result.what_this_means}</h3>
        <p className="text-gray-700 mb-4">{result.explanation}</p>
        
        <h4 className="font-semibold mb-2">What to do next:</h4>
        <ul className="space-y-2">
          {result.what_to_do_next.map((step: string, i: number) => (
            <li key={i} className="flex items-start gap-2">
              <span className="bg-blue-100 text-blue-600 rounded-full w-6 h-6 flex items-center justify-center text-sm font-bold shrink-0">
                {i + 1}
              </span>
              <span>{step}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* STI Breakdown */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h3 className="text-xl font-bold mb-4">STI Risk Breakdown</h3>
        <div className="space-y-3">
          {result.sti_risks.map((risk: { sti_type: string; probability: number; level: string }) => (
            <div key={risk.sti_type} className="flex items-center gap-4">
              <span className="w-24 font-medium capitalize">{risk.sti_type}</span>
              <div className="flex-1 bg-gray-200 rounded-full h-4">
                <div
                  className={`h-4 rounded-full transition-all ${
                    risk.probability > 0.5 ? 'bg-red-500' : 'bg-yellow-500'
                  }`}
                  style={{ width: `${risk.probability * 100}%` }}
                />
              </div>
              <span className="w-16 text-right">
                {(risk.probability * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Top Factors */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h3 className="text-xl font-bold mb-4">Key Risk Factors</h3>
        <div className="grid gap-3">
          {result.top_factors.map((factor: { factor: string; category: string; impact: string }, i: number) => (
            <div key={i} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
              <span className="text-2xl">
                {factor.category === 'symptom' ? '🩺' : '⚡'}
              </span>
              <div>
                <p className="font-medium capitalize">{factor.factor}</p>
                <p className="text-sm text-gray-500">{factor.impact}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-4">
        <button
          onClick={onFindClinics}
          className="flex-1 bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700"
        >
          Find Testing Clinics
        </button>
        <button
          onClick={onRetake}
          className="flex-1 border border-gray-300 py-3 rounded-lg font-semibold hover:bg-gray-50"
        >
          Retake Assessment
        </button>
      </div>

      {/* Disclaimer */}
      <p className="text-sm text-gray-500 mt-6 text-center">
        {result.disclaimer}
      </p>
    </div>
  );
};