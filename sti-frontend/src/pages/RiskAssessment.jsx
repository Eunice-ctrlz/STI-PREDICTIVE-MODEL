import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import {
  Activity, ChevronRight, AlertCircle, User, Heart,
  MapPin, Stethoscope, CheckCircle2
} from 'lucide-react'

const STEPS = [
  { id: 1, label: 'Patient Lookup', icon: User },
  { id: 2, label: 'Demographics', icon: User },
  { id: 3, label: 'Risk Factors', icon: Heart },
  { id: 4, label: 'Review', icon: CheckCircle2 },
]

export default function RiskAssessment() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [patientId, setPatientId] = useState('')
  const [patientData, setPatientData] = useState(null)
  const [formData, setFormData] = useState({
    patient_id: '',
    first_name: '',
    last_name: '',
    date_of_birth: '',
    gender: 'M',
    phone: '',
    email: '',
    county: '',
    sub_county: '',
    ward: '',
    marital_status: 'single',
    number_of_partners_12m: 0,
    number_of_partners_lifetime: 0,
    condom_use_frequency: 0.0,
    substance_use: false,
    substance_type: '',
    prior_sti_history: false,
    prior_sti_types: '',
    hiv_status_known: false,
    hiv_status: 'unknown',
    symptoms_present: false,
    symptom_description: '',
  })

  const handleSearchPatient = async (e) => {
    e.preventDefault()
    if (!patientId.trim()) { setStep(2); return }
    try {
      const res = await api.patients.get(patientId)
      setPatientData(res)
      setFormData(prev => ({ ...prev, ...res, patient_id: res.patient_id }))
      setStep(2)
    } catch {
      setFormData(prev => ({ ...prev, patient_id: patientId }))
      setStep(2)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      if (!patientData) await api.patients.create(formData)
      else await api.patients.update(formData.patient_id, formData)
      const predRes = await api.predictions.predict({
        patient_id: formData.patient_id,
        sti_type: 'general',
      })
      navigate(`/assess/result/${predRes.id}`)
    } catch (err) {
      setError(err.message || 'An error occurred')
    } finally {
      setLoading(false)
    }
  }

  const updateField = (field, value) => setFormData(prev => ({ ...prev, [field]: value }))

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-8">
        <h1 className="page-title flex items-center gap-2">
          <Activity className="w-6 h-6 text-accent" />
          STI Risk Assessment
        </h1>
        <p className="text-sm text-muted mt-1">Complete the assessment to generate a risk prediction</p>
      </div>

      {/* Progress Steps */}
      <div className="flex items-center mb-8">
        {STEPS.map((s, i) => (
          <div key={s.id} className="flex items-center flex-1">
            <div className={`
              flex items-center justify-center w-8 h-8 rounded-full text-xs font-bold transition-colors
              ${step >= s.id ? 'bg-accent text-white' : 'bg-gray-100 text-gray-400'}
            `}>
              {step > s.id ? <CheckCircle2 className="w-4 h-4" /> : s.id}
            </div>
            <span className={`ml-2 text-xs font-medium hidden sm:block ${step >= s.id ? 'text-primary' : 'text-gray-400'}`}>
              {s.label}
            </span>
            {i < STEPS.length - 1 && (
              <div className={`flex-1 h-px mx-3 ${step > s.id ? 'bg-accent' : 'bg-gray-200'}`} />
            )}
          </div>
        ))}
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl flex items-center gap-2 text-red-700 text-sm">
          <AlertCircle className="w-5 h-5 shrink-0" />
          {error}
        </div>
      )}

      {step === 1 && (
        <div className="card p-8">
          <h2 className="text-lg font-semibold mb-2">Patient Lookup</h2>
          <p className="text-sm text-muted mb-6">Enter an existing patient ID or proceed to create a new record.</p>
          <form onSubmit={handleSearchPatient} className="space-y-4">
            <div>
              <label className="label">Patient ID</label>
              <div className="flex gap-3">
                <input
                  type="text"
                  value={patientId}
                  onChange={(e) => setPatientId(e.target.value)}
                  placeholder="e.g., KNH-2024-001"
                  className="input-field flex-1"
                />
                <button type="submit" className="btn-primary whitespace-nowrap">Search</button>
              </div>
            </div>
            <button type="button" onClick={() => setStep(2)} className="text-accent text-sm font-medium hover:underline">
              Skip to new patient →
            </button>
          </form>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-6">
          <div className="card p-6">
            <h2 className="text-lg font-semibold mb-6 flex items-center gap-2">
              <User className="w-5 h-5 text-accent" />
              Demographics
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FormField label="Patient ID *" required>
                <input type="text" required value={formData.patient_id} onChange={(e) => updateField('patient_id', e.target.value)} className="input-field" />
              </FormField>
              <FormField label="First Name *" required>
                <input type="text" required value={formData.first_name} onChange={(e) => updateField('first_name', e.target.value)} className="input-field" />
              </FormField>
              <FormField label="Last Name *" required>
                <input type="text" required value={formData.last_name} onChange={(e) => updateField('last_name', e.target.value)} className="input-field" />
              </FormField>
              <FormField label="Date of Birth *" required>
                <input type="date" required value={formData.date_of_birth} onChange={(e) => updateField('date_of_birth', e.target.value)} className="input-field" />
              </FormField>
              <FormField label="Gender *" required>
                <select value={formData.gender} onChange={(e) => updateField('gender', e.target.value)} className="input-field">
                  <option value="M">Male</option>
                  <option value="F">Female</option>
                  <option value="O">Other</option>
                  <option value="U">Unknown</option>
                </select>
              </FormField>
              <FormField label="Phone">
                <input type="tel" value={formData.phone} onChange={(e) => updateField('phone', e.target.value)} className="input-field" />
              </FormField>
              <FormField label="County">
                <input type="text" value={formData.county} onChange={(e) => updateField('county', e.target.value)} className="input-field" placeholder="e.g., Nairobi" />
              </FormField>
              <FormField label="Sub-County">
                <input type="text" value={formData.sub_county} onChange={(e) => updateField('sub_county', e.target.value)} className="input-field" />
              </FormField>
            </div>
          </div>
          <div className="flex justify-end gap-3">
            <button onClick={() => setStep(1)} className="btn-ghost">Back</button>
            <button onClick={() => setStep(3)} className="btn-primary">Continue <ChevronRight className="w-4 h-4" /></button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-6">
          <div className="card p-6">
            <h2 className="text-lg font-semibold mb-6 flex items-center gap-2">
              <Heart className="w-5 h-5 text-accent" />
              Risk Factors
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FormField label="Marital Status">
                <select value={formData.marital_status} onChange={(e) => updateField('marital_status', e.target.value)} className="input-field">
                  <option value="single">Single</option>
                  <option value="married">Married</option>
                  <option value="divorced">Divorced</option>
                  <option value="widowed">Widowed</option>
                  <option value="cohabiting">Cohabiting</option>
                </select>
              </FormField>
              <FormField label="Partners (Last 12 Months)">
                <input type="number" min="0" value={formData.number_of_partners_12m} onChange={(e) => updateField('number_of_partners_12m', parseInt(e.target.value) || 0)} className="input-field" />
              </FormField>
              <FormField label="Condom Use Frequency">
                <div className="pt-2">
                  <input type="range" min="0" max="1" step="0.25" value={formData.condom_use_frequency} onChange={(e) => updateField('condom_use_frequency', parseFloat(e.target.value))} className="w-full accent-accent" />
                  <div className="flex justify-between text-xs text-muted mt-1">
                    <span>Never</span>
                    <span>Sometimes</span>
                    <span>Always</span>
                  </div>
                </div>
              </FormField>
              <FormField label="HIV Status">
                <select value={formData.hiv_status} onChange={(e) => updateField('hiv_status', e.target.value)} className="input-field">
                  <option value="unknown">Unknown</option>
                  <option value="negative">Negative</option>
                  <option value="positive">Positive</option>
                </select>
              </FormField>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
              <CheckboxField label="Substance Use" checked={formData.substance_use} onChange={(v) => updateField('substance_use', v)} />
              <CheckboxField label="Prior STI History" checked={formData.prior_sti_history} onChange={(v) => updateField('prior_sti_history', v)} />
              <CheckboxField label="Symptoms Present" checked={formData.symptoms_present} onChange={(v) => updateField('symptoms_present', v)} />
              <CheckboxField label="HIV Status Known" checked={formData.hiv_status_known} onChange={(v) => updateField('hiv_status_known', v)} />
            </div>
            {formData.symptoms_present && (
              <FormField label="Symptom Description" className="mt-4">
                <textarea rows={3} value={formData.symptom_description} onChange={(e) => updateField('symptom_description', e.target.value)} className="input-field" placeholder="Describe any symptoms..." />
              </FormField>
            )}
          </div>
          <div className="flex justify-end gap-3">
            <button onClick={() => setStep(2)} className="btn-ghost">Back</button>
            <button onClick={() => setStep(4)} className="btn-primary">Review <ChevronRight className="w-4 h-4" /></button>
          </div>
        </div>
      )}

      {step === 4 && (
        <div className="space-y-6">
          <div className="card p-6">
            <h2 className="text-lg font-semibold mb-6 flex items-center gap-2">
              <Stethoscope className="w-5 h-5 text-accent" />
              Review & Predict
            </h2>
            <div className="bg-gray-50 rounded-xl p-5 space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-4">
                <ReviewItem label="Patient" value={`${formData.first_name} ${formData.last_name}`} />
                <ReviewItem label="ID" value={formData.patient_id} />
                <ReviewItem label="Gender" value={formData.gender} />
                <ReviewItem label="County" value={formData.county || '—'} />
                <ReviewItem label="Partners (12m)" value={formData.number_of_partners_12m} />
                <ReviewItem label="Condom Use" value={`${(formData.condom_use_frequency * 100).toFixed(0)}%`} />
                <ReviewItem label="Prior STI" value={formData.prior_sti_history ? 'Yes' : 'No'} />
                <ReviewItem label="Substance Use" value={formData.substance_use ? 'Yes' : 'No'} />
                <ReviewItem label="HIV Status" value={formData.hiv_status} />
                <ReviewItem label="Symptoms" value={formData.symptoms_present ? 'Yes' : 'No'} />
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-3">
            <button onClick={() => setStep(3)} className="btn-ghost">Back</button>
            <button onClick={handleSubmit} disabled={loading} className="btn-primary">
              {loading ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                  Processing...
                </>
              ) : (
                <>Run Risk Prediction</>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function FormField({ label, children, required, className = '' }) {
  return (
    <div className={className}>
      <label className="label">{label}{required && <span className="text-red-500 ml-0.5">*</span>}</label>
      {children}
    </div>
  )
}

function CheckboxField({ label, checked, onChange }) {
  return (
    <label className="flex items-center gap-2.5 p-3 border border-border rounded-xl cursor-pointer hover:bg-gray-50 transition-colors">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="w-4 h-4 rounded border-gray-300 text-accent focus:ring-accent" />
      <span className="text-sm font-medium text-primary">{label}</span>
    </label>
  )
}

function ReviewItem({ label, value }) {
  return (
    <div className="flex justify-between py-1">
      <span className="text-muted">{label}</span>
      <span className="font-medium text-primary">{value}</span>
    </div>
  )
}