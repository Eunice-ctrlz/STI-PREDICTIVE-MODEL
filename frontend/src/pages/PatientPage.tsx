import React, { useState } from 'react';
import { SymptomChecklist } from '../components/patient/SymptomChecklist';
import type { SymptomResponse } from '../services/patientApi';

export const PatientPage: React.FC = () => {
  const [responses, setResponses] = useState<SymptomResponse[] | null>(null);

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-slate-900">Patient Assessment</h1>
        <p className="mt-2 text-slate-600">Complete the checklist to capture symptom responses.</p>
      </div>

      <SymptomChecklist onComplete={setResponses} />

      {responses && (
        <div className="mt-8 rounded-2xl border border-emerald-200 bg-emerald-50 p-6 text-emerald-900">
          <h2 className="text-xl font-semibold">Checklist complete</h2>
          <p className="mt-2">Captured {responses.length} symptom responses.</p>
        </div>
      )}
    </main>
  );
};
