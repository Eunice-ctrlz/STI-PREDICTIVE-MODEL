import React from 'react';
import { HeatmapViewer } from '../components/moh/HeatmapViewer';

export const MOHPage: React.FC = () => {
  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-slate-900">MOH Dashboard</h1>
        <p className="mt-2 text-slate-600">Monitor geographic hotspots and STI trends.</p>
      </div>
      <HeatmapViewer />
    </main>
  );
};
