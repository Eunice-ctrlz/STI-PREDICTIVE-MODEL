
        import type { PopulationSummary } from '../../services/clinicianApi';

interface Props {
  data: PopulationSummary;
}

export const PopulationView = ({ data }: Props) => {
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-bold mb-4">Population Summary</h2>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-lg bg-gray-50 p-4">
          <div className="text-sm text-gray-500">Patients Assessed</div>
          <div className="text-2xl font-bold">{data.total_patients_assessed}</div>
        </div>
        <div className="rounded-lg bg-gray-50 p-4">
          <div className="text-sm text-gray-500">New Alerts</div>
          <div className="text-2xl font-bold">{data.new_alerts}</div>
        </div>
        <div className="rounded-lg bg-gray-50 p-4">
          <div className="text-sm text-gray-500">Resolved Alerts</div>
          <div className="text-2xl font-bold">{data.resolved_alerts}</div>
        </div>
        <div className="rounded-lg bg-gray-50 p-4">
          <div className="text-sm text-gray-500">Reporting Period</div>
          <div className="text-lg font-bold">{data.reporting_period}</div>
        </div>
        <div className="rounded-lg bg-gray-50 p-4">
          <div className="text-sm text-gray-500">Trend</div>
          <div className={`text-2xl font-bold capitalize ${
            data.trend_direction === 'improving' ? 'text-green-600' :
            data.trend_direction === 'worsening' ? 'text-red-600' :
            'text-yellow-600'
          }`}>
            {data.trend_direction}
          </div>
        </div>
        {data.week_over_week_delta !== undefined && (
          <div className="rounded-lg bg-gray-50 p-4">
            <div className="text-sm text-gray-500">Week-over-Week</div>
            <div className={`text-2xl font-bold ${data.week_over_week_delta >= 0 ? 'text-red-600' : 'text-green-600'}`}>
              {data.week_over_week_delta >= 0 ? '+' : ''}{data.week_over_week_delta?.toFixed(1)}%
            </div>
          </div>
        )}
      </div>

      {/* Risk Distribution */}
      {data.risk_distribution && (
        <div className="mt-6">
          <h3 className="text-lg font-semibold mb-3">Risk Distribution</h3>
          <div className="space-y-2">
            {Object.entries(data.risk_distribution).map(([level, count]) => (
              <div key={level} className="flex items-center gap-3">
                <span className="w-20 capitalize text-sm font-medium">{level}</span>
                <div className="flex-1 bg-gray-200 rounded-full h-4">
                  <div
                    className={`h-4 rounded-full ${
                      level === 'critical' ? 'bg-red-600' :
                      level === 'high' ? 'bg-orange-500' :
                      level === 'moderate' ? 'bg-yellow-500' :
                      'bg-green-500'
                    }`}
                    style={{ width: `${(count / data.total_patients_assessed) * 100}%` }}
                  />
                </div>
                <span className="w-12 text-right text-sm">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* STI Distribution */}
      {data.sti_distribution && (
        <div className="mt-6">
          <h3 className="text-lg font-semibold mb-3">STI Distribution</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(data.sti_distribution).map(([sti, count]) => (
              <div key={sti} className="bg-blue-50 rounded-lg p-3">
                <div className="text-xs text-blue-600 uppercase font-medium">{sti}</div>
                <div className="text-xl font-bold text-blue-900">{count}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
