import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom'; // or your router
import { clinicianApi } from '../../services/clinicianApi';
import type { Alert, PopulationSummary } from '../../services/clinicianApi';
import { AlertQueue } from './AlertQueue';
import { PopulationView } from './PopulationView';

export const ClinicianDashboard: React.FC = () => {
  const navigate = useNavigate();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [population, setPopulation] = useState<PopulationSummary | null>(null);
  const [activeTab, setActiveTab] = useState<'alerts' | 'population' | 'differential'>('alerts');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Check auth before fetching
    const token = localStorage.getItem('clinician_token');
    if (!token) {
      navigate('/login'); // Redirect to login page
      return;
    }
    loadDashboardData();
  }, [navigate]);

  const loadDashboardData = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const [alertsRes, popRes] = await Promise.all([
        clinicianApi.getAlerts(),
        clinicianApi.getPopulationSummary(),
      ]);
      setAlerts(alertsRes.data.alerts);
      setPopulation(popRes.data);
    } catch (err: any) {
      console.error('Failed to load dashboard:', err);
      
      // Handle 401 specifically
      if (err.message?.includes('401') || err.message?.includes('Unauthorized')) {
        localStorage.removeItem('clinician_token');
        navigate('/login');
        return;
      }
      
      setError(err.message || 'Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  const handleAlertAction = async (alertId: string, action: string) => {
    try {
      await clinicianApi.processAlert(alertId, action);
      loadDashboardData();
    } catch (error: any) {
      console.error('Failed to process alert:', error);
      if (error.message?.includes('401')) {
        localStorage.removeItem('clinician_token');
        navigate('/login');
      }
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('clinician_token');
    navigate('/login');
  };

  if (loading) return <div className="p-8 text-center">Loading dashboard...</div>;
  
  if (error) return (
    <div className="p-8 text-center">
      <div className="text-red-600 mb-4">{error}</div>
      <button 
        onClick={loadDashboardData}
        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
      >
        Retry
      </button>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Clinician Dashboard</h1>
            <p className="text-sm text-gray-500">STI Predictive Model - Kenya MOH</p>
          </div>
          <div className="flex items-center gap-4">
            <div className="bg-red-100 text-red-700 px-4 py-2 rounded-lg font-medium">
              {alerts.filter(a => a.status === 'new' && a.risk_level === 'critical').length} Critical Alerts
            </div>
            <button 
              onClick={handleLogout}
              className="text-gray-600 hover:text-gray-900"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-8">
            {(['alerts', 'population', 'differential'] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`py-4 border-b-2 font-medium capitalize ${
                  activeTab === tab
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                {tab === 'alerts' && `Patient Alerts (${alerts.filter(a => a.status === 'new').length})`}
                {tab === 'population' && 'Population View'}
                {tab === 'differential' && 'Differential Diagnosis'}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {activeTab === 'alerts' && (
          <AlertQueue
            alerts={alerts}
            onAction={handleAlertAction}
          />
        )}
        
        {activeTab === 'population' && population && (
          <PopulationView data={population} />
        )}
        
        {activeTab === 'differential' && (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-bold mb-4">Symptom-Driven Differential</h2>
            <p className="text-gray-600">Enter symptoms to get ranked STI differentials with probability scores.</p>
          </div>
        )}
      </main>
    </div>
  );
};