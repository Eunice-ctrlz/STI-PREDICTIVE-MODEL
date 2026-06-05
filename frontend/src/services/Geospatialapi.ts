// src/services/geospatialApi.ts

import { api } from './api';

export interface HeatmapFeature {
  geometry: { coordinates: [number, number] };
  properties: {
    risk_level: string;
    risk_score: number;
    incident_count: number;
    county: string;
  };
}

export interface HeatmapData {
  sti_type: string;
  geojson: {
    type: string;
    features: HeatmapFeature[];
  };
  total_cells: number;
  hotspot_cells: number;
}

export const geospatialApi = {
  getHeatmap: (county: string, stiType = 'all') =>
    api.get<HeatmapData>(
      `/api/v1/geospatial/heatmap?county=${encodeURIComponent(county)}&sti_type=${stiType}`
    ),

  getHotspots: (county?: string, stiType?: string) => {
    const params = new URLSearchParams();
    if (county) params.append('county', county);
    if (stiType) params.append('sti_type', stiType);
    const query = params.toString() ? `?${params.toString()}` : '';
    return api.get<Array<{
      hotspot_id: string;
      county: string;
      sub_county: string;
      sti_type: string;
      risk_score: number;
      risk_level: string;
      incident_count: number;
      coordinates: [number, number];
    }>>(`/api/v1/geospatial/hotspots${query}`);
  },

  getCountySummary: (county: string) =>
    api.get<{
      county: string;
      overall_risk_level: string;
      total_cases: number;
      sti_breakdown: Record<string, number>;
      trend: string;
    }>(`/api/v1/geospatial/county/${encodeURIComponent(county)}/summary`),
};