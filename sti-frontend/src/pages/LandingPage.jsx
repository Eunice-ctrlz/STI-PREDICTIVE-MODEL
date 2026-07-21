import { useNavigate } from 'react-router-dom'
import { 
  ShieldCheck, Activity, Brain, Map, ArrowRight, 
  CheckCircle, BarChart3, Lock, Users
} from 'lucide-react'

export default function LandingPage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-white">
      {/* Navbar */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-md border-b border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
                <ShieldCheck className="w-4 h-4 text-white" />
              </div>
              <span className="font-bold text-primary">STI Predictor</span>
            </div>
            <div className="hidden md:flex items-center gap-6">
              <a href="#features" className="text-sm text-muted hover:text-primary transition-colors">Features</a>
              <a href="#how-it-works" className="text-sm text-muted hover:text-primary transition-colors">How it Works</a>
              <a href="#impact" className="text-sm text-muted hover:text-primary transition-colors">Impact</a>
              <button 
                onClick={() => navigate('/dashboard')}
                className="btn-primary text-sm py-2 px-4"
              >
                Open Dashboard
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="pt-32 pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className="space-y-8">
              <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-accent/10 text-accent rounded-full text-xs font-semibold">
                <Activity className="w-3.5 h-3.5" />
                Clinical Intelligence Platform
              </div>
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-primary leading-tight">
                Predicting Health,<br />
                <span className="text-accent">Protecting Kenya</span>
              </h1>
              <p className="text-lg text-muted max-w-lg leading-relaxed">
                AI-powered STI risk prediction for clinicians and public health officials. 
                Real-time screening, geospatial analytics, and MOH reporting — all in one platform.
              </p>
              <div className="flex flex-wrap gap-4">
                <button 
                  onClick={() => navigate('/dashboard')}
                  className="btn-primary text-base py-3 px-6"
                >
                  Start Screening <ArrowRight className="w-4 h-4" />
                </button>
                <button 
                  onClick={() => navigate('/assess')}
                  className="btn-ghost text-base py-3 px-6 border border-border"
                >
                  Risk Assessment
                </button>
              </div>
              <div className="flex items-center gap-6 text-sm text-muted">
                <div className="flex items-center gap-1.5">
                  <CheckCircle className="w-4 h-4 text-emerald-500" />
                  <span>HIPAA Compliant</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <CheckCircle className="w-4 h-4 text-emerald-500" />
                  <span>MOH Integrated</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <CheckCircle className="w-4 h-4 text-emerald-500" />
                  <span>Real-time</span>
                </div>
              </div>
            </div>
            <div className="relative">
              <div className="absolute -inset-4 bg-gradient-to-br from-accent/10 to-primary/5 rounded-3xl blur-2xl" />
              <div className="relative card p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-muted uppercase tracking-wider font-semibold">Risk Score</p>
                    <p className="text-3xl font-bold text-red-500">72.4%</p>
                  </div>
                  <div className="w-12 h-12 rounded-full bg-red-50 flex items-center justify-center">
                    <Activity className="w-6 h-6 text-red-500" />
                  </div>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div className="h-full bg-red-500 rounded-full" style={{ width: '72.4%' }} />
                </div>
                <div className="grid grid-cols-3 gap-3 pt-2">
                  <div className="text-center p-3 bg-gray-50 rounded-xl">
                    <p className="text-lg font-bold text-primary">1,247</p>
                    <p className="text-[10px] text-muted">Screenings</p>
                  </div>
                  <div className="text-center p-3 bg-gray-50 rounded-xl">
                    <p className="text-lg font-bold text-primary">342</p>
                    <p className="text-[10px] text-muted">High Risk</p>
                  </div>
                  <div className="text-center p-3 bg-gray-50 rounded-xl">
                    <p className="text-lg font-bold text-primary">47</p>
                    <p className="text-[10px] text-muted">Counties</p>
                  </div>
                </div>
                <div className="p-3 bg-amber-50 rounded-xl border border-amber-100">
                  <p className="text-xs text-amber-700 font-medium">Recommended: Immediate comprehensive STI screening</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-20 bg-gray-50/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-primary mb-4">Platform Features</h2>
            <p className="text-muted max-w-2xl mx-auto">Everything clinicians and public health officials need for STI prevention and control.</p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            <FeatureCard 
              icon={Brain}
              title="AI Prediction"
              description="Machine learning models trained on clinical data to predict STI risk with 89% accuracy."
              color="blue"
            />
            <FeatureCard 
              icon={Map}
              title="Geospatial Analytics"
              description="Interactive heatmaps showing risk distribution across all 47 Kenyan counties."
              color="teal"
            />
            <FeatureCard 
              icon={BarChart3}
              title="MOH Reporting"
              description="Automated reports for the Ministry of Health with real-time epidemiological data."
              color="indigo"
            />
            <FeatureCard 
              icon={Lock}
              title="Compliance"
              description="Full audit trails, patient consent management, and data retention policies."
              color="emerald"
            />
          </div>
        </div>
      </section>

      {/* How it Works */}
      <section id="how-it-works" className="py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-primary mb-4">How It Works</h2>
            <p className="text-muted max-w-2xl mx-auto">From patient intake to public health insight in four simple steps.</p>
          </div>
          <div className="grid md:grid-cols-4 gap-8">
            {[
              { step: '01', title: 'Patient Intake', desc: 'Enter patient demographics and risk factors through a streamlined form.' },
              { step: '02', title: 'AI Assessment', desc: 'Our ML model analyzes risk factors and generates a probability score.' },
              { step: '03', title: 'Clinical Decision', desc: 'Review recommended tests and actions based on the risk level.' },
              { step: '04', title: 'Public Health', desc: 'Aggregated data feeds into MOH dashboards and geospatial maps.' },
            ].map((item, i) => (
              <div key={i} className="relative">
                <div className="text-5xl font-bold text-gray-100 mb-4">{item.step}</div>
                <h3 className="font-semibold text-primary mb-2">{item.title}</h3>
                <p className="text-sm text-muted leading-relaxed">{item.desc}</p>
                {i < 3 && (
                  <div className="hidden md:block absolute top-8 right-0 w-full h-px bg-gradient-to-r from-border to-transparent" />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Impact Stats */}
      <section id="impact" className="py-20 bg-primary text-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold mb-4">Platform Impact</h2>
            <p className="text-gray-400 max-w-2xl mx-auto">Making a measurable difference in STI prevention across Kenya.</p>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8">
            <ImpactStat number="12,450" label="Total Screenings" />
            <ImpactStat number="3,280" label="High-Risk Identified" />
            <ImpactStat number="89%" label="Model Accuracy" />
            <ImpactStat number="47" label="Counties Covered" />
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="text-3xl font-bold text-primary mb-4">Ready to get started?</h2>
          <p className="text-muted mb-8 max-w-lg mx-auto">Join healthcare providers across Kenya using AI to predict and prevent STI transmission.</p>
          <button 
            onClick={() => navigate('/dashboard')}
            className="btn-primary text-lg py-3 px-8"
          >
            Launch Platform <ArrowRight className="w-5 h-5" />
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-primary flex items-center justify-center">
              <ShieldCheck className="w-3 h-3 text-white" />
            </div>
            <span className="text-sm font-semibold text-primary">STI Predictor</span>
          </div>
          <p className="text-xs text-muted">Clinical Intelligence Platform for STI Prevention. Kenya Ministry of Health Integrated.</p>
          <p className="text-xs text-muted">2026 STI Predictor. All rights reserved.</p>
        </div>
      </footer>
    </div>
  )
}

function FeatureCard({ icon: Icon, title, description, color }) {
  const colors = {
    blue: 'bg-blue-50 text-blue-600',
    teal: 'bg-teal-50 text-teal-600',
    indigo: 'bg-indigo-50 text-indigo-600',
    emerald: 'bg-emerald-50 text-emerald-600',
  }
  return (
    <div className="card p-6 hover:shadow-card-hover transition-shadow">
      <div className={`w-10 h-10 rounded-xl ${colors[color]} flex items-center justify-center mb-4`}>
        <Icon className="w-5 h-5" />
      </div>
      <h3 className="font-semibold text-primary mb-2">{title}</h3>
      <p className="text-sm text-muted leading-relaxed">{description}</p>
    </div>
  )
}

function ImpactStat({ number, label }) {
  return (
    <div className="text-center">
      <p className="text-4xl font-bold mb-2">{number}</p>
      <p className="text-sm text-gray-400">{label}</p>
    </div>
  )
}