const API_BASE = import.meta.env.VITE_API_URL || '/api';

/** Drop undefined/empty params so we don't send `?county=&days=` to the API. */
function qs(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      search.append(key, value);
    }
  });
  const str = search.toString();
  return str ? `?${str}` : '';
}

async function fetchApi(path, options = {}) {
  const url = `${API_BASE}${path}`;

  let res;
  try {
    res = await fetch(url, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    });
  } catch {
    // fetch only rejects on network-level failures, which for this app almost
    // always means the Django server isn't running.
    throw new Error('Cannot reach the API server. Is the Django backend running on port 8000?');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    // django-ninja returns validation errors as detail: [{loc, msg}, ...]
    if (Array.isArray(err.detail)) {
      const messages = err.detail
        .map((d) => `${(d.loc || []).slice(-1)[0] || 'field'}: ${d.msg}`)
        .join('; ');
      throw new Error(messages || `HTTP ${res.status}`);
    }
    throw new Error(err.detail || err.message || `HTTP ${res.status}`);
  }

  if (res.status === 204) return null;
  return res.json();
}

const post = (path, data) => fetchApi(path, { method: 'POST', body: JSON.stringify(data) });

export const api = {
  patients: {
    list: (params) => fetchApi(`/patients/${qs(params)}`),
    get: (id) => fetchApi(`/patients/${encodeURIComponent(id)}`),
    create: (data) => post('/patients/', data),
    update: (id, data) =>
      fetchApi(`/patients/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(data) }),
    delete: (id) => fetchApi(`/patients/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  },

  predictions: {
    predict: (data) => post('/predictions/predict', data),
    batch: (data) => post('/predictions/predict/batch', data),
    get: (id) => fetchApi(`/predictions/${id}`),
    history: (patientId) => fetchApi(`/predictions/history/${encodeURIComponent(patientId)}`),
    stats: (params) => fetchApi(`/predictions/stats${qs(params)}`),
    performance: (params) => fetchApi(`/predictions/performance${qs(params)}`),
    validate: (id, params) => post(`/predictions/validate/${id}${qs(params)}`),
  },

  reporting: {
    dashboard: (params) => fetchApi(`/reporting/dashboard${qs(params)}`),
    templates: () => fetchApi('/reporting/templates'),
    reports: (params) => fetchApi(`/reporting/reports${qs(params)}`),
  },

  geospatial: {
    heatmap: (params) => fetchApi(`/geospatial/heatmap${qs(params)}`),
    countySummary: () => fetchApi('/geospatial/county-summary'),
    riskZones: (params) => fetchApi(`/geospatial/risk-zones${qs(params)}`),
  },

  ml: {
    models: (params) => fetchApi(`/ml/models${qs(params)}`),
    model: (id) => fetchApi(`/ml/models/${id}`),
    deploy: (id) => post(`/ml/models/${id}/deploy`),
    jobs: (params) => fetchApi(`/ml/jobs${qs(params)}`),
    job: (id) => fetchApi(`/ml/jobs/${id}`),
  },

  compliance: {
    auditLogs: (params) => fetchApi(`/compliance/audit-logs${qs(params)}`),
    auditSummary: (params) => fetchApi(`/compliance/audit-logs/summary${qs(params)}`),
    consents: (patientId) => fetchApi(`/compliance/consents/${encodeURIComponent(patientId)}`),
    retentionPolicies: () => fetchApi('/compliance/retention-policies'),
  },

  clinicians: {
    list: () => fetchApi('/clinicians/'),
    facilities: () => fetchApi('/clinicians/facilities'),
    facility: (id) => fetchApi(`/clinicians/facilities/${id}`),
  },

  ingestion: {
    jobs: () => fetchApi('/ingestion/jobs'),
  },

  /**
   * AI explanation layer. Entirely optional: every call here can fail without
   * affecting the prediction endpoints above, so callers are expected to
   * degrade rather than surface an error state.
   */
  ai: {
    status: () => fetchApi('/ai/status'),
    explainPrediction: (predictionId, { refresh = false } = {}) =>
      post('/ai/explain-prediction', { prediction_id: predictionId, refresh }),
    storedExplanation: (predictionId) => fetchApi(`/ai/explanation/${predictionId}`),
  },
};
