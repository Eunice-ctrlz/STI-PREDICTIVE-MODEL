// App.js
import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import PatientDashboard from './pages/PatientDashboard';
import ClinicianView from './pages/ClinicianView';
import GeospatialHeatmap from './pages/GeospatialHeatmap';
import MOHReporting from './pages/MOHReporting';
import Login from './pages/Login';
import RiskAssessment from './pages/RiskAssessment';
import './styles/globals.css';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userRole, setUserRole] = useState(null);

  useEffect(() => {
    const token = localStorage.getItem('authToken');
    const role = localStorage.getItem('userRole');
    if (token && role) {
      setIsAuthenticated(true);
      setUserRole(role);
    }
  }, []);

  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login setIsAuthenticated={setIsAuthenticated} setUserRole={setUserRole} />} />
        <Route path="/" element={isAuthenticated ? <Layout userRole={userRole} /> : <Navigate to="/login" />}>
          <Route index element={<Dashboard userRole={userRole} />} />
          <Route path="patient" element={<PatientDashboard />} />
          <Route path="patient/risk-assessment" element={<RiskAssessment />} />
          <Route path="clinician" element={<ClinicianView />} />
          <Route path="heatmap" element={<GeospatialHeatmap />} />
          <Route path="moh-reporting" element={<MOHReporting />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;