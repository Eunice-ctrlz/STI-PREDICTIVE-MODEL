import { api } from './api';

export interface HeatmapData {
  sti_type: string;
  geojson: {
    type: string;
    features: Array<{
      geometry: { coordinates: [number, number] };
      properties: {
        risk_level: string;
        risk_score: number;
        incident_count: number;
        county: string;
      };
    }>;
  };
  total_cells: number;
  hotspot_cells: number;
}

export interface HotspotData {
  hotspot_id: string;
  county: string;
  sub_county: string;
  sti_type: string;
  risk_score: number;
  risk_level: string;
  incident_count: number;
  coordinates: [number, number];
}

export const geospatialApi = {
  getHeatmap: (county: string, stiType: string = 'all') =>
    api.get<HeatmapData>(
      `/api/v1/geospatial/heatmap?county=${encodeURIComponent(county)}&sti_type=${stiType}`
    ),

  getHotspots: (county?: string, stiType?: string) =>
    api.get<HotspotData[]>(
      `/api/v1/geospatial/hotspots${county ? `?county=${encodeURIComponent(county)}` : ''}${stiType ? `&sti_type=${stiType}` : ''}`
    ),

  getCountyRiskSummary: (county: string) =>
    api.get<{
      county: string;
      overall_risk_level: string;
      total_cases: number;
      sti_breakdown: Record<string, number>;
      trend: string;
    }>(`/api/v1/geospatial/county/${encodeURIComponent(county)}/summary`),
};