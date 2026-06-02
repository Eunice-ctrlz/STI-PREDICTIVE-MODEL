import React, { useState, useEffect } from 'react';
import { patientApi } from '../../services/patientApi';
import type { SymptomResponse } from '../../services/patientApi';

interface Props {
  onComplete: (responses: SymptomResponse[]) => void;
  language?: 'en' | 'sw';
}

export const SymptomChecklist: React.FC<Props> = ({ onComplete, language = 'en' }) => {
  const [questions, setQuestions] = useState<Array<{
    symptom_id: string;
    question_text: string;
    category: string;
    help_text?: string;
  }>>([]);
  const [responses, setResponses] = useState<Record<string, SymptomResponse>>({});
  const [loading, setLoading] = useState(true);
  const [currentStep, setCurrentStep] = useState(0);

  useEffect(() => {
    loadQuestions();
  }, [language]);

  const loadQuestions = async () => {
    try {
      const { data } = await patientApi.getSymptomQuestions();
      setQuestions(data);
      setLoading(false);
    } catch (error) {
      console.error('Failed to load questions:', error);
    }
  };

  const handleResponse = (symptomId: string, present: boolean) => {
    setResponses(prev => ({
      ...prev,
      [symptomId]: {
        symptom_id: symptomId,
        present,
      },
    }));
  };

  const categories = [...new Set(questions.map(q => q.category))];
  const currentCategory = categories[currentStep];
  const categoryQuestions = questions.filter(q => q.category === currentCategory);

  const progress = ((currentStep + 1) / categories.length) * 100;

  if (loading) return <div className="text-center py-8">Loading...</div>;

  return (
    <div className="max-w-2xl mx-auto p-6 bg-white rounded-lg shadow">
      {/* Progress bar */}
      <div className="mb-6">
        <div className="flex justify-between text-sm text-gray-600 mb-2">
          <span>Step {currentStep + 1} of {categories.length}</span>
          <span>{Math.round(progress)}% complete</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-blue-600 h-2 rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <h2 className="text-2xl font-bold mb-4 capitalize">
        {currentCategory.replace('_', ' ')} Symptoms
      </h2>

      <div className="space-y-4">
        {categoryQuestions.map(question => (
          <div key={question.symptom_id} className="border rounded-lg p-4">
            <p className="font-medium mb-3">{question.question_text}</p>
            {question.help_text && (
              <p className="text-sm text-gray-500 mb-3">{question.help_text}</p>
            )}
            <div className="flex gap-4">
              <button
                onClick={() => handleResponse(question.symptom_id, true)}
                className={`px-6 py-2 rounded-lg font-medium transition ${
                  responses[question.symptom_id]?.present
                    ? 'bg-red-500 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                Yes
              </button>
              <button
                onClick={() => handleResponse(question.symptom_id, false)}
                className={`px-6 py-2 rounded-lg font-medium transition ${
                  responses[question.symptom_id]?.present === false
                    ? 'bg-green-500 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                No
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="flex justify-between mt-8">
        <button
          onClick={() => setCurrentStep(Math.max(0, currentStep - 1))}
          disabled={currentStep === 0}
          className="px-6 py-2 rounded-lg border border-gray-300 disabled:opacity-50"
        >
          Back
        </button>
        
        {currentStep < categories.length - 1 ? (
          <button
            onClick={() => setCurrentStep(currentStep + 1)}
            className="px-6 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700"
          >
            Next
          </button>
        ) : (
          <button
            onClick={() => onComplete(Object.values(responses))}
            className="px-6 py-2 rounded-lg bg-green-600 text-white hover:bg-green-700"
          >
            Get My Risk Assessment
          </button>
        )}
      </div>
    </div>
  );
};