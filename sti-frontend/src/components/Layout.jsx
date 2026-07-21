import { Outlet, NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Users, Activity, Map, FileText,
  Brain, Shield, ShieldCheck, Menu, X, ChevronRight,
  Bell, Search
} from 'lucide-react'
import { useState } from 'react'

const navItems = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/patients', label: 'Patients', icon: Users },
  { path: '/assess', label: 'Risk Assessment', icon: Activity },
  { path: '/heatmap', label: 'Risk Map', icon: Map },
  { path: '/reports', label: 'MOH Reports', icon: FileText },
  { path: '/models', label: 'ML Models', icon: Brain },
  { path: '/audit', label: 'Audit Logs', icon: Shield },
]

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const location = useLocation()
  const isLanding = location.pathname === '/'

  if (isLanding) return <Outlet />

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 lg:hidden backdrop-blur-sm"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed lg:static inset-y-0 left-0 z-50 w-[260px] bg-primary flex flex-col
        transition-transform duration-300 ease-out
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        {/* Logo */}
        <div className="flex items-center gap-3 px-5 py-5 border-b border-white/10">
          <div className="w-9 h-9 rounded-xl bg-accent flex items-center justify-center">
            <ShieldCheck className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-white font-bold text-sm leading-tight">STI Predictor</h1>
            <p className="text-gray-400 text-[10px] leading-tight">Clinical Intelligence</p>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden ml-auto text-gray-400 hover:text-white"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) => `
    flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200
    ${isActive
                  ? 'bg-white/10 text-white shadow-sm'
                  : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
                }
  `}
            >
              {({ isActive }) => (
                <>
                  <item.icon className="w-[18px] h-[18px]" />
                  <span>{item.label}</span>
                  {isActive && <ChevronRight className="w-4 h-4 ml-auto opacity-50" />}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* User profile */}
        <div className="p-3 border-t border-white/10">
          <div className="flex items-center gap-3 px-3 py-2 rounded-xl bg-white/5">
            <div className="w-8 h-8 rounded-lg bg-accent/20 flex items-center justify-center">
              <span className="text-accent text-xs font-bold">DR</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white text-sm font-medium truncate">Dr. User</p>
              <p className="text-gray-500 text-xs truncate">Clinician</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top bar */}
        <header className="h-16 bg-surface border-b border-border flex items-center justify-between px-4 lg:px-6 shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden p-2 hover:bg-gray-100 rounded-lg"
            >
              <Menu className="w-5 h-5 text-gray-600" />
            </button>
            <div className="hidden md:flex items-center gap-2 text-sm text-muted">
              <span className="font-medium text-primary">Platform</span>
              <ChevronRight className="w-3 h-3" />
              <span>{navItems.find(n => n.path === location.pathname)?.label || 'Dashboard'}</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center gap-2 px-3 py-1.5 bg-gray-50 rounded-lg border border-border">
              <Search className="w-4 h-4 text-muted" />
              <input
                type="text"
                placeholder="Search patients..."
                className="bg-transparent text-sm outline-none w-48 placeholder:text-gray-400"
              />
            </div>
            <button className="relative p-2 hover:bg-gray-100 rounded-lg">
              <Bell className="w-5 h-5 text-gray-600" />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full" />
            </button>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}