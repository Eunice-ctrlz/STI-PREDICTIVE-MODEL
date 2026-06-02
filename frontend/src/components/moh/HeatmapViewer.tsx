import React, { useState, useEffect } from 'react';
import { geospatialApi } from '../../services/Geospatialapi';

interface HeatmapData {
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

export const HeatmapViewer: React.FC = () => {
  const [county, setCounty] = useState('Nairobi');
  const [stiType, setStiType] = useState('all');
  const [heatmap, setHeatmap] = useState<HeatmapData | null>(null);
  const [loading, setLoading] = useState(false);

  const counties = ['Nairobi', 'Mombasa', 'Kisumu', 'Nakuru', 'Kiambu', 'Kilifi'];
  const stiTypes = [
    { value: 'all', label: 'All STIs' },
    { value: 'hiv', label: 'HIV' },
    { value: 'chlamydia', label: 'Chlamydia' },
    { value: 'syphilis', label: 'Syphilis' },
    { value: 'gonorrhoea', label: 'Gonorrhoea' },
  ];

  useEffect(() => {
    loadHeatmap();
  }, [county, stiType]);

  const loadHeatmap = async () => {
    setLoading(true);
    try {
      const { data } = await geospatialApi.getHeatmap(county, stiType);
      setHeatmap(data);
    } catch (error) {
      console.error('Failed to load heatmap:', error);
    } finally {
      setLoading(false);
    }
  };

  const getRiskColor = (level: string) => {
    switch (level) {
      case 'low': return 'bg-green-500';
      case 'moderate': return 'bg-yellow-500';
      case 'high': return 'bg-orange-500';
      case 'critical': return 'bg-red-600';
      default: return 'bg-gray-400';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow">
      {/* Controls */}
      <div className="p-4 border-b flex gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">County</label>
          <select
            value={county}
            onChange={e => setCounty(e.target.value)}
            className="border rounded-lg px-4 py-2 w-48"
          >
            {counties.map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">STI Type</label>
          <select
            value={stiType}
            onChange={e => setStiType(e.target.value)}
            className="border rounded-lg px-4 py-2 w-48"
          >
            {stiTypes.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Stats */}
      {heatmap && (
        <div className="p-4 bg-gray-50 flex gap-8">
          <div>
            <div className="text-2xl font-bold">{heatmap.total_cells}</div>
            <div className="text-sm text-gray-500">Total Grid Cells</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-red-600">{heatmap.hotspot_cells}</div>
            <div className="text-sm text-gray-500">Hotspot Cells</div>
          </div>
        </div>
      )}

      {/* Map Visualization (Simplified) */}
      <div className="p-4">
        {loading ? (
          <div className="h-96 flex items-center justify-center">
            Loading heatmap data...
          </div>
        ) : heatmap ? (
          <div className="grid grid-cols-8 gap-1">
            {heatmap.geojson.features.map((feature, i) => (
              <div
                key={i}
                className={`aspect-square rounded ${getRiskColor(feature.properties.risk_level)} hover:opacity-80 cursor-pointer transition`}
                title={`${feature.properties.county}: ${feature.properties.risk_level} (${(feature.properties.risk_score * 100).toFixed(0)}%)`}
              />
            ))}
          </div>
        ) : (
          <div className="h-96 flex items-center justify-center text-gray-500">
            No heatmap data available
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="p-4 border-t flex gap-6 justify-center">
        {[
          { level: 'low', label: 'Low Risk', color: 'bg-green-500' },
          { level: 'moderate', label: 'Moderate', color: 'bg-yellow-500' },
          { level: 'high', label: 'High Risk', color: 'bg-orange-500' },
          { level: 'critical', label: 'Critical', color: 'bg-red-600' },
        ].map(item => (
          <div key={item.level} className="flex items-center gap-2">
            <div className={`w-4 h-4 rounded ${item.color}`} />
            <span className="text-sm">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
};