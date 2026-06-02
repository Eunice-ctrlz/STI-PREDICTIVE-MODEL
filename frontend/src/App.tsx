import React from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import { PatientPage } from './pages/PatientPage';
import { ClinicianPage } from './pages/ClinicianPage';
import { MOHPage } from './pages/MOHPage';
import { LandingPage } from './pages/LandingPage';

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50">
        {/* Navigation */}
        <nav className="bg-white shadow-sm">
          <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
            <Link to="/" className="text-xl font-bold text-blue-600">
              STI Predictive Model
            </Link>
            <div className="flex gap-6">
              <Link to="/patient" className="text-gray-600 hover:text-blue-600">
                Patient Assessment
              </Link>
              <Link to="/clinician" className="text-gray-600 hover:text-blue-600">
                Clinician Portal
              </Link>
              <Link to="/moh" className="text-gray-600 hover:text-blue-600">
                MOH Dashboard
              </Link>
            </div>
          </div>
        </nav>

        {/* Routes */}
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/patient" element={<PatientPage />} />
          <Route path="/clinician" element={<ClinicianPage />} />
          <Route path="/moh" element={<MOHPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
};

export default App;