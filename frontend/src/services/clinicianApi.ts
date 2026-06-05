// src/services/clinicianApi.ts

import { api } from './api';

export interface Alert {
  alert_id: string;
  anonymous_id: string;
  risk_score: number;
  risk_level: string;
  sti_probabilities: Record<string, number>;
  top_features: Array<{
    feature: string;
    contribution: string;
    description: string;
  }>;
  status: string;
  triggered_at: string;
  clinician_notes?: string;
  recommended_action?: string;
}

export interface AlertSummary {
  total_new: number;
  total_acknowledged: number;
  total_under_review: number;
  total_critical_unacknowledged: number;
  avg_risk_score?: number;
  alerts: Alert[];
}

export interface PopulationSummary {
  summary_id: string;
  reporting_period: string;
  total_patients_assessed: number;
  risk_distribution: Record<string, number>;
  sti_distribution: Record<string, number>;
  new_alerts: number;
  resolved_alerts: number;
  week_over_week_delta?: number;
  trend_direction: 'improving' | 'stable' | 'worsening' | 'unknown';
}

export const clinicianApi = {
  login: (username: string, password: string) =>
    api.post<{ token: string; clinician_id: string }>(
      '/clinicians/login',
      { username, password }
    ),


  getProfile: () =>
    api.get<{
      clinician_id: string;
      full_name: string;
      role: string;
      facility_name: string;
      facility_county: string;
    }>('/clinicians/profile'),

  getAlerts: (status?: string) =>
    api.get<AlertSummary>(
      `/clinicians/alerts${status ? `?status=${status}` : ''}`
    ),

  processAlert: (alertId: string, action: string, notes?: string) =>
    api.post<Alert>(`/clinicians/alerts/${alertId}/action`, {
      action,
      clinician_notes: notes,
    }),

  getPopulationSummary: (county?: string) =>
    api.get<PopulationSummary>(
      `/clinicians/population/summary${county ? `?county=${county}` : ''}`
    ),

  getDifferential: (
    symptoms: string[],
    demographics: Record<string, unknown>,
    region: string
  ) =>
    api.post<{
      ranked_differentials: Array<{
        sti_type: string;
        probability_estimate: number;
        key_symptoms: string[];
        recommended_tests: string[];
      }>;
      urgency_level: 'routine' | 'urgent' | 'emergency';
    }>('/clinicians/differential', {
      symptoms,
      demographics,
      geographic_region: region,
    }),
};