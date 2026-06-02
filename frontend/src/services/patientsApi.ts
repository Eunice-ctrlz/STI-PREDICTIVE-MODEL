import { api } from './api';

export interface SymptomResponse {
  symptom_id: string;
  present: boolean;
  severity?: 'mild' | 'moderate' | 'severe';
  duration_days?: number;
}

export interface AssessmentRequest {
  symptoms: {
    responses: SymptomResponse[];
  };
  behaviours: {
    partner_count_12m: number;
    new_partners_3m: number;
    condom_use_frequency: 'never' | 'sometimes' | 'often' | 'always';
    prior_sti_test_12m: boolean;
    prior_sti_diagnosis: string[];
    substance_use_alcohol_drugs: boolean;
    sex_work_involvement: boolean;
  };
  demographics: {
    age: number;
    sex: 'male' | 'female' | 'other' | 'prefer_not_say';
    county: string;
    sub_county?: string;
  };
  consent_reminders: boolean;
  consent_tracking: boolean;
  language: 'en' | 'sw';
  session_id?: string;
}

export interface STIRisk {
  sti_type: string;
  probability: number;
  level: string;
}

export interface AssessmentResult {
  assessment_id: string;
  session_id: string;
  overall_risk_level: 'low' | 'moderate' | 'high' | 'critical';
  overall_risk_score: number;
  sti_risks: STIRisk[];
  top_factors: Array<{
    factor: string;
    category: string;
    impact: string;
  }>;
  explanation: string;
  what_this_means: string;
  what_to_do_next: string[];
  mandatory_clinical_review: boolean;
  nearest_clinics: Array<{
    name: string;
    distance_km: number;
    services: string[];
    walk_in: boolean;
  }>;
  disclaimer: string;
}

export const patientApi = {
  createSession: (county?: string, language: 'en' | 'sw' = 'en') =>
    api.post<{ session_id: string; expires_at: string }>(
      '/api/v1/patients/session/create',
      { county, language }
    ),

  getSymptomQuestions: () =>
    api.get<Array<{
      symptom_id: string;
      question_text: string;
      category: string;
      help_text?: string;
    }>>('/api/v1/patients/symptoms/questions'),

  submitAssessment: (data: AssessmentRequest) =>
    api.post<AssessmentResult>('/api/v1/patients/assess', data),

  findClinics: (county: string, sub_county?: string, max_distance_km: number = 50) =>
    api.post<Array<{
      facility_id: string;
      name: string;
      county: string;
      sub_county: string;
      services: string[];
      distance_km: number;
      walk_in_accepted: boolean;
    }>>('/api/v1/patients/clinics/nearby', {
      county,
      sub_county,
      max_distance_km,
    }),
};