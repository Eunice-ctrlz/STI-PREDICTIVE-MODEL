import React from 'react';
import { Link } from 'react-router-dom';

export const LandingPage: React.FC = () => {
  return (
    <main className="min-h-[calc(100vh-5rem)] bg-slate-50">
      <section className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-20 md:flex-row md:items-center md:justify-between">
        <div className="max-w-2xl">
          <p className="mb-4 text-sm font-semibold uppercase tracking-[0.3em] text-blue-600">STI Predictive Model</p>
          <h1 className="text-4xl font-black tracking-tight text-slate-900 md:text-6xl">Risk assessment, clinician triage, and geospatial monitoring in one workflow.</h1>
          <p className="mt-6 text-lg leading-8 text-slate-600">
            A React frontend for patient screening, clinician review, and Ministry of Health oversight.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <Link to="/patient" className="rounded-full bg-blue-600 px-6 py-3 font-semibold text-white hover:bg-blue-700">
              Start patient assessment
            </Link>
            <Link to="/clinician" className="rounded-full border border-slate-300 px-6 py-3 font-semibold text-slate-700 hover:bg-white">
              Open clinician dashboard
            </Link>
          </div>
        </div>
        <div className="rounded-3xl bg-white p-6 shadow-xl shadow-slate-200/60 ring-1 ring-slate-200 md:w-[28rem]">
          <div className="grid gap-4">
            <div className="rounded-2xl bg-blue-50 p-4">
              <div className="text-sm text-blue-700">Patient flow</div>
              <div className="mt-1 text-xl font-bold text-slate-900">Symptom checklist to risk result</div>
            </div>
            <div className="rounded-2xl bg-emerald-50 p-4">
              <div className="text-sm text-emerald-700">Clinician flow</div>
              <div className="mt-1 text-xl font-bold text-slate-900">Alerts, population summary, differential support</div>
            </div>
            <div className="rounded-2xl bg-amber-50 p-4">
              <div className="text-sm text-amber-700">MOH flow</div>
              <div className="mt-1 text-xl font-bold text-slate-900">Heatmap and hotspot monitoring</div>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
};
