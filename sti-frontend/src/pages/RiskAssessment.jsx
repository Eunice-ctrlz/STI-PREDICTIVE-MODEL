import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Activity, AlertCircle, CheckCircle2, ChevronRight,
  Heart, Loader2, Search, Stethoscope, User,
} from 'lucide-react'
import { api } from '../lib/api'
import { formatGender, humanize } from '../lib/utils'

const STEPS = [
  { id: 1, label: 'Patient Lookup', icon: Search },
  { id: 2, label: 'Demographics', icon: User },
  { id: 3, label: 'Risk Factors', icon: Heart },
  { id: 4, label: 'Review', icon: CheckCircle2 },
]

const EMPTY_FORM = {
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
}

/** Only the fields the API accepts — strips id/age/created_at etc. */
function toPayload(form) {
  return Object.fromEntries(Object.keys(EMPTY_FORM).map((key) => [key, form[key]]))
}

export default function RiskAssessment() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const prefillId = searchParams.get('patient') || ''

  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [lookupLoading, setLookupLoading] = useState(false)
  const [error, setError] = useState('')
  const [lookupNote, setLookupNote] = useState('')
  const [patientId, setPatientId] = useState(prefillId)
  const [existingPatient, setExistingPatient] = useState(null)
  const [formData, setFormData] = useState(EMPTY_FORM)

  const updateField = (field, value) => setFormData((prev) => ({ ...prev, [field]: value }))

  const loadPatient = async (id) => {
    setLookupLoading(true)
    setError('')
    setLookupNote('')
    try {
      const res = await api.patients.get(id)
      setExistingPatient(res)
      // Keep only known form keys so server-computed fields never round-trip.
      setFormData({ ...EMPTY_FORM, ...toPayload(res), patient_id: res.patient_id })
      setLookupNote(`Loaded existing record for ${res.first_name} ${res.last_name}.`)
      setStep(2)
    } catch {
      setExistingPatient(null)
      setFormData({ ...EMPTY_FORM, patient_id: id })
      setLookupNote(`No record found for "${id}" — continue to create a new patient.`)
      setStep(2)
    } finally {
      setLookupLoading(false)
    }
  }

  // Deep link from the patient list: /assess?patient=KNH-2024-001
  useEffect(() => {
    if (prefillId) loadPatient(prefillId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefillId])

  const handleLookup = (e) => {
    e.preventDefault()
    const id = patientId.trim()
    if (!id) {
      setStep(2)
      return
    }
    loadPatient(id)
  }

  const canContinueFromDemographics =
    formData.patient_id.trim() &&
    formData.first_name.trim() &&
    formData.last_name.trim() &&
    formData.date_of_birth

  const handleSubmit = async () => {
    setLoading(true)
    setError('')
    try {
      const payload = toPayload(formData)
      if (existingPatient) {
        await api.patients.update(formData.patient_id, payload)
      } else {
        await api.patients.create(payload)
      }
      const prediction = await api.predictions.predict({
        patient_id: formData.patient_id,
        sti_type: 'general',
      })
      navigate(`/assess/result/${prediction.id}`)
    } catch (err) {
      setError(err.message || 'An error occurred')
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-8">
        <h1 className="page-title flex items-center gap-2">
          <Activity className="h-6 w-6 text-accent" />
          STI Risk Assessment
        </h1>
        <p className="page-subtitle">Complete the assessment to generate a risk prediction</p>
      </div>

      <ol className="mb-8 flex items-center">
        {STEPS.map((s, i) => (
          <li key={s.id} className="flex flex-1 items-center">
            <button
              type="button"
              onClick={() => s.id < step && setStep(s.id)}
              disabled={s.id >= step}
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                step >= s.id ? 'bg-accent text-white' : 'bg-gray-100 text-gray-400'
              } ${s.id < step ? 'cursor-pointer hover:bg-accent-light' : ''}`}
              aria-current={step === s.id ? 'step' : undefined}
            >
              {step > s.id ? <CheckCircle2 className="h-4 w-4" /> : s.id}
            </button>
            <span
              className={`ml-2 hidden text-xs font-medium sm:block ${
                step >= s.id ? 'text-primary' : 'text-gray-400'
              }`}
            >
              {s.label}
            </span>
            {i < STEPS.length - 1 && (
              <div className={`mx-3 h-px flex-1 ${step > s.id ? 'bg-accent' : 'bg-gray-200'}`} />
            )}
          </li>
        ))}
      </ol>

      {error && (
        <div className="mb-6 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {step === 1 && (
        <div className="card p-8">
          <h2 className="mb-2 text-lg font-semibold text-primary">Patient Lookup</h2>
          <p className="mb-6 text-sm text-muted">
            Enter an existing patient ID to re-assess, or skip to register a new patient.
          </p>
          <form onSubmit={handleLookup} className="space-y-4">
            <div>
              <label htmlFor="lookup" className="label">Patient ID</label>
              <div className="flex gap-3">
                <input
                  id="lookup"
                  type="text"
                  value={patientId}
                  onChange={(e) => setPatientId(e.target.value)}
                  placeholder="e.g. KNH-2024-001"
                  className="input-field flex-1"
                />
                <button type="submit" disabled={lookupLoading} className="btn-primary whitespace-nowrap">
                  {lookupLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                  Search
                </button>
              </div>
            </div>
            <button
              type="button"
              onClick={() => { setExistingPatient(null); setFormData(EMPTY_FORM); setStep(2) }}
              className="text-sm font-medium text-accent hover:underline"
            >
              Skip to new patient →
            </button>
          </form>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-6">
          {lookupNote && (
            <div
              className={`rounded-xl border p-4 text-sm ${
                existingPatient
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                  : 'border-blue-200 bg-blue-50 text-blue-800'
              }`}
            >
              {lookupNote}
            </div>
          )}

          <div className="card p-6">
            <h2 className="mb-6 flex items-center gap-2 text-lg font-semibold text-primary">
              <User className="h-5 w-5 text-accent" />
              Demographics
            </h2>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <FormField label="Patient ID" htmlFor="patient_id" required>
                <input
                  id="patient_id"
                  type="text"
                  required
                  disabled={Boolean(existingPatient)}
                  value={formData.patient_id}
                  onChange={(e) => updateField('patient_id', e.target.value)}
                  className="input-field"
                />
              </FormField>
              <FormField label="First Name" htmlFor="first_name" required>
                <input id="first_name" type="text" required value={formData.first_name}
                  onChange={(e) => updateField('first_name', e.target.value)} className="input-field" />
              </FormField>
              <FormField label="Last Name" htmlFor="last_name" required>
                <input id="last_name" type="text" required value={formData.last_name}
                  onChange={(e) => updateField('last_name', e.target.value)} className="input-field" />
              </FormField>
              <FormField label="Date of Birth" htmlFor="dob" required>
                <input id="dob" type="date" required max={new Date().toISOString().split('T')[0]}
                  value={formData.date_of_birth}
                  onChange={(e) => updateField('date_of_birth', e.target.value)} className="input-field" />
              </FormField>
              <FormField label="Gender" htmlFor="gender" required>
                <select id="gender" value={formData.gender}
                  onChange={(e) => updateField('gender', e.target.value)} className="input-field">
                  <option value="M">Male</option>
                  <option value="F">Female</option>
                  <option value="O">Other</option>
                  <option value="U">Unknown</option>
                </select>
              </FormField>
              <FormField label="Phone" htmlFor="phone">
                <input id="phone" type="tel" value={formData.phone}
                  onChange={(e) => updateField('phone', e.target.value)} className="input-field"
                  placeholder="+254…" />
              </FormField>
              <FormField label="County" htmlFor="county">
                <input id="county" type="text" value={formData.county}
                  onChange={(e) => updateField('county', e.target.value)} className="input-field"
                  placeholder="e.g. Nairobi" />
              </FormField>
              <FormField label="Sub-County" htmlFor="sub_county">
                <input id="sub_county" type="text" value={formData.sub_county}
                  onChange={(e) => updateField('sub_county', e.target.value)} className="input-field" />
              </FormField>
            </div>
          </div>

          <div className="flex justify-end gap-3">
            <button onClick={() => setStep(1)} className="btn-ghost">Back</button>
            <button
              onClick={() => setStep(3)}
              disabled={!canContinueFromDemographics}
              className="btn-primary"
            >
              Continue <ChevronRight className="h-4 w-4" />
            </button>
          </div>
          {!canContinueFromDemographics && (
            <p className="text-right text-xs text-muted">
              Patient ID, name and date of birth are required to continue.
            </p>
          )}
        </div>
      )}

      {step === 3 && (
        <div className="space-y-6">
          <div className="card p-6">
            <h2 className="mb-6 flex items-center gap-2 text-lg font-semibold text-primary">
              <Heart className="h-5 w-5 text-accent" />
              Risk Factors
            </h2>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <FormField label="Marital Status" htmlFor="marital">
                <select id="marital" value={formData.marital_status}
                  onChange={(e) => updateField('marital_status', e.target.value)} className="input-field">
                  {['single', 'married', 'divorced', 'widowed', 'cohabiting'].map((s) => (
                    <option key={s} value={s}>{humanize(s)}</option>
                  ))}
                </select>
              </FormField>
              <FormField label="HIV Status" htmlFor="hiv">
                <select id="hiv" value={formData.hiv_status}
                  onChange={(e) => updateField('hiv_status', e.target.value)} className="input-field">
                  <option value="unknown">Unknown</option>
                  <option value="negative">Negative</option>
                  <option value="positive">Positive</option>
                </select>
              </FormField>
              <FormField label="Partners (last 12 months)" htmlFor="p12">
                <input id="p12" type="number" min="0" value={formData.number_of_partners_12m}
                  onChange={(e) => updateField('number_of_partners_12m', Math.max(0, parseInt(e.target.value, 10) || 0))}
                  className="input-field" />
              </FormField>
              <FormField label="Partners (lifetime)" htmlFor="plife">
                <input id="plife" type="number" min="0" value={formData.number_of_partners_lifetime}
                  onChange={(e) => updateField('number_of_partners_lifetime', Math.max(0, parseInt(e.target.value, 10) || 0))}
                  className="input-field" />
              </FormField>
              <FormField
                label={`Condom Use Frequency — ${(formData.condom_use_frequency * 100).toFixed(0)}%`}
                htmlFor="condom"
                className="md:col-span-2"
              >
                <div className="pt-2">
                  <input id="condom" type="range" min="0" max="1" step="0.25"
                    value={formData.condom_use_frequency}
                    onChange={(e) => updateField('condom_use_frequency', parseFloat(e.target.value))}
                    className="w-full accent-accent" />
                  <div className="mt-1 flex justify-between text-xs text-muted">
                    <span>Never</span><span>Sometimes</span><span>Always</span>
                  </div>
                </div>
              </FormField>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
              <CheckboxField label="Substance Use" checked={formData.substance_use}
                onChange={(v) => updateField('substance_use', v)} />
              <CheckboxField label="Prior STI History" checked={formData.prior_sti_history}
                onChange={(v) => updateField('prior_sti_history', v)} />
              <CheckboxField label="Symptoms Present" checked={formData.symptoms_present}
                onChange={(v) => updateField('symptoms_present', v)} />
              <CheckboxField label="HIV Status Known" checked={formData.hiv_status_known}
                onChange={(v) => updateField('hiv_status_known', v)} />
            </div>

            {(formData.substance_use || formData.prior_sti_history || formData.symptoms_present) && (
              <div className="mt-5 space-y-4 border-t border-border pt-5">
                {formData.substance_use && (
                  <FormField label="Substance Type" htmlFor="substance_type">
                    <input id="substance_type" type="text" value={formData.substance_type}
                      onChange={(e) => updateField('substance_type', e.target.value)}
                      className="input-field" placeholder="e.g. alcohol, injectable drugs" />
                  </FormField>
                )}
                {formData.prior_sti_history && (
                  <FormField label="Prior STI Types" htmlFor="prior_sti_types">
                    <input id="prior_sti_types" type="text" value={formData.prior_sti_types}
                      onChange={(e) => updateField('prior_sti_types', e.target.value)}
                      className="input-field" placeholder="e.g. chlamydia, gonorrhoea" />
                  </FormField>
                )}
                {formData.symptoms_present && (
                  <FormField label="Symptom Description" htmlFor="symptom_description">
                    <textarea id="symptom_description" rows={3} value={formData.symptom_description}
                      onChange={(e) => updateField('symptom_description', e.target.value)}
                      className="input-field" placeholder="Describe any symptoms…" />
                  </FormField>
                )}
              </div>
            )}
          </div>

          <div className="flex justify-end gap-3">
            <button onClick={() => setStep(2)} className="btn-ghost">Back</button>
            <button onClick={() => setStep(4)} className="btn-primary">
              Review <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {step === 4 && (
        <div className="space-y-6">
          <div className="card p-6">
            <h2 className="mb-6 flex items-center gap-2 text-lg font-semibold text-primary">
              <Stethoscope className="h-5 w-5 text-accent" />
              Review &amp; Predict
            </h2>
            <dl className="grid grid-cols-1 gap-x-8 gap-y-1 rounded-xl bg-gray-50 p-5 text-sm sm:grid-cols-2">
              <ReviewItem label="Patient" value={`${formData.first_name} ${formData.last_name}`} />
              <ReviewItem label="ID" value={formData.patient_id} />
              <ReviewItem label="Date of Birth" value={formData.date_of_birth} />
              <ReviewItem label="Gender" value={formatGender(formData.gender)} />
              <ReviewItem label="County" value={formData.county || '—'} />
              <ReviewItem label="Marital Status" value={humanize(formData.marital_status)} />
              <ReviewItem label="Partners (12m)" value={formData.number_of_partners_12m} />
              <ReviewItem label="Partners (lifetime)" value={formData.number_of_partners_lifetime} />
              <ReviewItem label="Condom Use" value={`${(formData.condom_use_frequency * 100).toFixed(0)}%`} />
              <ReviewItem label="HIV Status" value={humanize(formData.hiv_status)} />
              <ReviewItem label="Prior STI" value={formData.prior_sti_history ? 'Yes' : 'No'} />
              <ReviewItem label="Substance Use" value={formData.substance_use ? 'Yes' : 'No'} />
              <ReviewItem label="Symptoms" value={formData.symptoms_present ? 'Yes' : 'No'} />
            </dl>
            <p className="mt-4 text-xs text-muted">
              {existingPatient
                ? 'This will update the existing patient record and generate a new prediction.'
                : 'This will create a new patient record and generate their first prediction.'}
            </p>
          </div>

          <div className="flex justify-end gap-3">
            <button onClick={() => setStep(3)} className="btn-ghost" disabled={loading}>Back</button>
            <button onClick={handleSubmit} disabled={loading} className="btn-primary">
              {loading ? (
                <><Loader2 className="h-4 w-4 animate-spin" /> Processing…</>
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

function FormField({ label, children, required, htmlFor, className = '' }) {
  return (
    <div className={className}>
      <label htmlFor={htmlFor} className="label">
        {label}
        {required && <span className="ml-0.5 text-red-500">*</span>}
      </label>
      {children}
    </div>
  )
}

function CheckboxField({ label, checked, onChange }) {
  return (
    <label
      className={`flex cursor-pointer items-center gap-2.5 rounded-xl border p-3 transition-colors ${
        checked ? 'border-accent/50 bg-accent/5' : 'border-border hover:bg-gray-50'
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 rounded border-gray-300 text-accent focus:ring-accent"
      />
      <span className="text-sm font-medium text-primary">{label}</span>
    </label>
  )
}

function ReviewItem({ label, value }) {
  return (
    <div className="flex justify-between gap-4 border-b border-border/60 py-2 last:border-0">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-medium text-primary">{value}</dd>
    </div>
  )
}
