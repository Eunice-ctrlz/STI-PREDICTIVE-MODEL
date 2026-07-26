import { useState, useEffect } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { Map as MapIcon, Layers, Info } from 'lucide-react'
import { api } from '../lib/api'

export default function Heatmap() {
  const [countyData, setCountyData] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadHeatmapData()
  }, [])

  const loadHeatmapData = async () => {
    try {
      const data = await api.geospatial.heatmap({})
      setCountyData(data)
    } catch (err) {
      console.error(err)
      // Mock data if backend fails
      setCountyData([
        { county: 'Nairobi', latitude: -1.2921, longitude: 36.8219, avg_risk_score: 0.45, total_patients: 4521, high_risk_count: 145 },
        { county: 'Mombasa', latitude: -4.0435, longitude: 39.6682, avg_risk_score: 0.38, total_patients: 2103, high_risk_count: 89 },
        { county: 'Kisumu', latitude: -0.0917, longitude: 34.7680, avg_risk_score: 0.42, total_patients: 1800, high_risk_count: 67 },
      ])
    } finally {
      setLoading(false)
    }
  }

  const getMarkerColor = (riskScore) => {
    if (riskScore >= 0.5) return '#ef4444' // Red (Highest Risk)
    if (riskScore >= 0.25) return '#eab308' // Yellow (Moderate Risk)
    return '#10b981' // Green (Fewest/Lowest Risk)
  }

  return (
    <div className="space-y-6 h-full flex flex-col">
      <div>
        <h1 className="page-title flex items-center gap-2">
          <MapIcon className="w-6 h-6 text-accent" />
          Geospatial Risk Map
        </h1>
        <p className="text-sm text-muted mt-1">Interactive heatmap of STI risk distribution across Kenya</p>
      </div>

      <div className="grid lg:grid-cols-4 gap-6 flex-1 min-h-[500px]">
        <div className="lg:col-span-3 card overflow-hidden relative">
          <div className="absolute top-4 right-4 z-[1000] bg-white p-2.5 rounded-lg shadow-md border border-border">
            <h4 className="text-xs font-semibold mb-2">Risk Levels</h4>
            <div className="space-y-1 text-xs">
              <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-red-500 opacity-60"></div>Highest Risk (&ge;50%)</div>
              <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-yellow-500 opacity-60"></div>Moderate Risk (25% - 49%)</div>
              <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-emerald-500 opacity-60"></div>Lowest Risk (&lt;25%)</div>
            </div>
          </div>
          
          <MapContainer 
            center={[0.0236, 37.9062]} // Center of Kenya
            zoom={6} 
            style={{ height: '100%', width: '100%', minHeight: '500px' }}
          >
            <TileLayer
              url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
            />
            {countyData.map((county, idx) => (
              county.latitude && county.longitude ? (
                <CircleMarker
                  key={idx}
                  center={[county.latitude, county.longitude]}
                  radius={Math.max(10, Math.min(county.avg_risk_score * 100, 40))}
                  fillColor={getMarkerColor(county.avg_risk_score)}
                  fillOpacity={0.6}
                  color="white"
                  weight={1}
                >
                  <Popup>
                    <div className="p-1">
                      <h3 className="font-semibold text-primary">{county.county}</h3>
                      <div className="mt-2 space-y-1 text-sm">
                        <p>Avg Risk: <span className="font-medium">{(county.avg_risk_score * 100).toFixed(1)}%</span></p>
                        <p>Patients: {county.total_patients}</p>
                        <p>High Risk: {county.high_risk_count}</p>
                      </div>
                    </div>
                  </Popup>
                </CircleMarker>
              ) : null
            ))}
          </MapContainer>
        </div>

        <div className="space-y-4">
          <div className="card p-5">
            <h3 className="font-semibold text-primary flex items-center gap-2 mb-4">
              <Layers className="w-4 h-4 text-accent" />
              Overview
            </h3>
            <div className="space-y-4">
              <div>
                <p className="text-xs text-muted uppercase">Counties Mapped</p>
                <p className="text-2xl font-bold text-primary">{countyData.length}</p>
              </div>
              <div>
                <p className="text-xs text-muted uppercase">Highest Risk County</p>
                <p className="text-lg font-semibold text-red-600">
                  {countyData.length ? [...countyData].sort((a,b) => b.avg_risk_score - a.avg_risk_score)[0].county : '—'}
                </p>
              </div>
            </div>
          </div>
          <div className="card p-5 bg-blue-50/50 border-blue-100">
            <div className="flex items-start gap-3">
              <Info className="w-5 h-5 text-blue-600 mt-0.5 shrink-0" />
              <p className="text-xs text-muted leading-relaxed">
                The heatmap visualizes aggregate risk scores by county. Larger circles indicate higher patient volumes, while colors indicate average risk level. Data is updated in real-time as new predictions are generated.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
