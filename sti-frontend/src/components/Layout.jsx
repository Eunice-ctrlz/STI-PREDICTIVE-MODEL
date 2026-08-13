import { useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  Activity, Brain, ChevronRight, FileText, LayoutDashboard,
  Map, Menu, Search, Settings, Shield, ShieldCheck, Users, X,
} from 'lucide-react'

const navItems = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/patients', label: 'Patients', icon: Users },
  { path: '/assess', label: 'Risk Assessment', icon: Activity },
  { path: '/heatmap', label: 'Risk Map', icon: Map },
  { path: '/reports', label: 'MOH Reports', icon: FileText },
  { path: '/models', label: 'ML Models', icon: Brain },
  { path: '/audit', label: 'Audit Logs', icon: Shield },
  { path: '/settings', label: 'Settings', icon: Settings },
]

/** Longest matching nav path, so /patients/KNH-1 still reads "Patients". */
function currentSection(pathname) {
  return navItems
    .filter((item) => pathname === item.path || pathname.startsWith(`${item.path}/`))
    .sort((a, b) => b.path.length - a.path.length)[0]
}

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [query, setQuery] = useState('')
  const location = useLocation()
  const navigate = useNavigate()

  const section = currentSection(location.pathname)

  const handleSearch = (e) => {
    e.preventDefault()
    const term = query.trim()
    if (!term) return
    navigate(`/patients?search=${encodeURIComponent(term)}`)
    setQuery('')
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-[260px] flex-col bg-primary transition-transform duration-300 ease-out lg:static ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        <div className="flex items-center gap-3 border-b border-white/10 px-5 py-5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent">
            <ShieldCheck className="h-5 w-5 text-white" />
          </div>
          <div className="min-w-0">
            <h1 className="text-sm font-bold leading-tight text-white">STI Predictor</h1>
            <p className="text-[10px] leading-tight text-gray-400">Clinical Intelligence</p>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="ml-auto text-gray-400 hover:text-white lg:hidden"
            aria-label="Close menu"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-4 py-2.5 text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-white/10 text-white shadow-sm'
                    : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <item.icon className="h-[18px] w-[18px] shrink-0" />
                  <span className="truncate">{item.label}</span>
                  {isActive && <ChevronRight className="ml-auto h-4 w-4 shrink-0 opacity-50" />}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-white/10 p-3">
          <div className="flex items-center gap-3 rounded-xl bg-white/5 px-3 py-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent/20">
              <span className="text-xs font-bold text-accent">DR</span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-white">Clinician</p>
              <p className="truncate text-xs text-gray-500">Not signed in</p>
            </div>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-surface px-4 lg:px-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              className="rounded-lg p-2 hover:bg-gray-100 lg:hidden"
              aria-label="Open menu"
            >
              <Menu className="h-5 w-5 text-gray-600" />
            </button>
            <nav aria-label="Breadcrumb" className="hidden items-center gap-2 text-sm text-muted md:flex">
              <span className="font-medium text-primary">Platform</span>
              <ChevronRight className="h-3 w-3" />
              <span>{section?.label || 'Dashboard'}</span>
            </nav>
          </div>

          <form
            onSubmit={handleSearch}
            className="flex items-center gap-2 rounded-lg border border-border bg-gray-50 px-3 py-1.5 focus-within:border-accent focus-within:bg-white"
          >
            <Search className="h-4 w-4 shrink-0 text-muted" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search patients…"
              aria-label="Search patients"
              className="w-32 bg-transparent text-sm outline-none placeholder:text-gray-400 sm:w-48"
            />
          </form>
        </header>

        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
