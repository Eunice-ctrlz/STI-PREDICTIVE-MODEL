const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

async function fetchApi(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.message || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  patients: {
    list: (params) => {
      const qs = new URLSearchParams(params).toString();
      return fetchApi(`/patients/?${qs}`);
    },
    get: (id) => fetchApi(`/patients/${id}`),
    create: (data) => fetchApi('/patients/', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => fetchApi(`/patients/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    delete: (id) => fetchApi(`/patients/${id}`, { method: 'DELETE' }),
  },
  predictions: {
    predict: (data) => fetchApi('/predictions/predict', { method: 'POST', body: JSON.stringify(data) }),
    get: (id) => fetchApi(`/predictions/${id}`),
    history: (patientId) => fetchApi(`/predictions/history/${patientId}`),
    stats: (params) => {
      const qs = new URLSearchParams(params).toString();
      return fetchApi(`/predictions/stats?${qs}`);
    },
  },
  reporting: {
    dashboard: (params) => {
      const qs = new URLSearchParams(params).toString();
      return fetchApi(`/reporting/dashboard?${qs}`);
    },
  },
  geospatial: {
    heatmap: (params) => {
      const qs = new URLSearchParams(params).toString();
      return fetchApi(`/geospatial/heatmap?${qs}`);
    },
    countySummary: () => fetchApi('/geospatial/county-summary'),
  },
};