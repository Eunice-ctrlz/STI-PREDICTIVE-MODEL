import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { Info, Layers, Map as MapIcon, X } from 'lucide-react'
import { api } from '../lib/api'
import { useApi } from '../hooks/useData'
import { EmptyState, ErrorState, LoadingState } from '../components/States'
import { formatNumber } from '../lib/utils'

const KENYA_CENTER = [0.0236, 37.9062]

const RISK_BANDS = [
  { min: 0.5, color: '#ef4444', label: 'Highest risk (≥50%)' },
  { min: 0.25, color: '#eab308', label: 'Moderate risk (25–49%)' },
  { min: 0, color: '#10b981', label: 'Lowest risk (<25%)' },
]

function markerColor(riskScore) {
  return RISK_BANDS.find((band) => riskScore >= band.min)?.color || '#10b981'
}

export default function Heatmap() {
  const [searchParams, setSearchParams] = useSearchParams()
  const county = searchParams.get('county') || ''

  const { data, loading, error, refetch } = useApi(
    () => api.geospatial.heatmap({ county }),
    [county]
  )

  const points = useMemo(
    () => (data || []).filter((p) => p.latitude != null && p.longitude != null),
    [data]
  )

  const highestRisk = useMemo(() => {
    if (points.length === 0) return null
    return [...points].sort((a, b) => b.avg_risk_score - a.avg_risk_score)[0]
  }, [points])

  const totalPatients = points.reduce((sum, p) => sum + (p.total_patients || 0), 0)

  return (
    <div className="flex h-full flex-col space-y-6">
      <div className="page-header">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <MapIcon className="h-6 w-6 text-accent" />
            Geospatial Risk Map
          </h1>
          <p className="page-subtitle">Aggregate STI risk by location across Kenya</p>
        </div>
        {county && (
          <button onClick={() => setSearchParams({})} className="btn-ghost text-sm">
            <X className="h-4 w-4" />
            Clear filter: {county}
          </button>
        )}
      </div>

      {error ? (
        <ErrorState error={error} onRetry={refetch} title="Could not load map data" />
      ) : (
        <div className="grid min-h-[520px] flex-1 gap-6 lg:grid-cols-4">
          <div className="relative overflow-hidden card lg:col-span-3">
            {loading ? (
              <LoadingState label="Loading map data…" className="h-full min-h-[520px]" />
            ) : (
              <>
                <div className="absolute right-4 top-4 z-[1000] rounded-lg border border-border bg-white p-3 shadow-md">
                  <h4 className="mb-2 text-xs font-semibold text-primary">Risk Levels</h4>
                  <div className="space-y-1.5 text-xs text-muted">
                    {RISK_BANDS.map((band) => (
                      <div key={band.label} className="flex items-center gap-2">
                        <span
                          className="h-3 w-3 rounded-full opacity-70"
                          style={{ backgroundColor: band.color }}
                        />
                        {band.label}
                      </div>
                    ))}
                  </div>
                </div>

                {points.length === 0 && (
                  <div className="absolute left-1/2 top-1/2 z-[1000] w-full max-w-sm -translate-x-1/2 -translate-y-1/2">
                    <div className="rounded-2xl border border-border bg-white/95 shadow-lg backdrop-blur">
                      <EmptyState
                        icon={MapIcon}
                        title="No mapped activity"
                        description={
                          county
                            ? `No predictions recorded for ${county} in the last 90 days.`
                            : 'Risk points appear once patients with a recorded county have predictions.'
                        }
                        className="py-8"
                      />
                    </div>
                  </div>
                )}

                <MapContainer
                  center={KENYA_CENTER}
                  zoom={6}
                  style={{ height: '100%', width: '100%', minHeight: '520px' }}
                  scrollWheelZoom
                >
                  <TileLayer
                    url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
                  />
                  {points.map((point, idx) => (
                    <CircleMarker
                      key={`${point.county}-${point.sub_county}-${idx}`}
                      center={[point.latitude, point.longitude]}
                      radius={Math.max(10, Math.min(point.avg_risk_score * 100, 40))}
                      pathOptions={{
                        fillColor: markerColor(point.avg_risk_score),
                        fillOpacity: 0.6,
                        color: 'white',
                        weight: 1,
                      }}
                    >
                      <Popup>
                        <div className="p-1">
                          <h3 className="font-semibold text-primary">{point.county}</h3>
                          {point.sub_county && (
                            <p className="text-xs text-muted">{point.sub_county}</p>
                          )}
                          <div className="mt-2 space-y-1 text-sm">
                            <p>
                              Avg risk:{' '}
                              <span className="font-medium">
                                {(point.avg_risk_score * 100).toFixed(1)}%
                              </span>
                            </p>
                            <p>Patients: {formatNumber(point.total_patients)}</p>
                            <p>High risk: {formatNumber(point.high_risk_count)}</p>
                          </div>
                        </div>
                      </Popup>
                    </CircleMarker>
                  ))}
                </MapContainer>
              </>
            )}
          </div>

          <div className="space-y-4">
            <div className="card p-5">
              <h3 className="mb-4 flex items-center gap-2 font-semibold text-primary">
                <Layers className="h-4 w-4 text-accent" />
                Overview
              </h3>
              <div className="space-y-4">
                <Stat label="Locations mapped" value={loading ? '—' : formatNumber(points.length)} />
                <Stat label="Patients covered" value={loading ? '—' : formatNumber(totalPatients)} />
                <div>
                  <p className="text-xs uppercase tracking-wider text-muted">Highest risk area</p>
                  {loading ? (
                    <p className="text-lg font-semibold text-muted">—</p>
                  ) : highestRisk ? (
                    <>
                      <p className="text-lg font-semibold text-red-600">{highestRisk.county}</p>
                      <p className="text-xs text-muted">
                        {(highestRisk.avg_risk_score * 100).toFixed(1)}% average risk
                      </p>
                    </>
                  ) : (
                    <p className="text-lg font-semibold text-muted">No data</p>
                  )}
                </div>
              </div>
            </div>

            <div className="card-flat border-blue-100 bg-blue-50/50 p-5">
              <div className="flex items-start gap-3">
                <Info className="mt-0.5 h-5 w-5 shrink-0 text-blue-600" />
                <p className="text-xs leading-relaxed text-muted">
                  Circle size reflects average risk and colour the risk band, aggregated over the
                  last 90 days of predictions. Points are plotted from county centroids, so they
                  indicate the county rather than an exact patient location.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wider text-muted">{label}</p>
      <p className="text-2xl font-bold text-primary">{value}</p>
    </div>
  )
}
