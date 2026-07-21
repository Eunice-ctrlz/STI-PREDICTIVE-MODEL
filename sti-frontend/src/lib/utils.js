import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export function formatDate(date) {
  return new Date(date).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function formatNumber(num) {
  return new Intl.NumberFormat('en-US').format(num);
}

export const RISK_CONFIG = {
  low: {
    label: 'Low Risk',
    color: 'emerald',
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    bar: 'bg-emerald-500',
    icon: 'Shield',
    message: 'Continue routine screening per guidelines. Reinforce safer sex practices. Annual rescreening recommended.',
  },
  moderate: {
    label: 'Moderate Risk',
    color: 'amber',
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
    bar: 'bg-amber-500',
    icon: 'AlertTriangle',
    message: 'Routine STI screening recommended. Provide condom counseling and risk reduction education. Schedule follow-up in 3 months.',
  },
  high: {
    label: 'High Risk',
    color: 'orange',
    bg: 'bg-orange-50',
    text: 'text-orange-700',
    border: 'border-orange-200',
    bar: 'bg-orange-500',
    icon: 'AlertTriangle',
    message: 'Immediate comprehensive STI screening recommended. Provide risk reduction counseling. Consider PrEP evaluation for HIV. Partner notification and contact tracing. Follow-up in 2-4 weeks.',
  },
  very_high: {
    label: 'Very High Risk',
    color: 'red',
    bg: 'bg-red-50',
    text: 'text-red-700',
    border: 'border-red-200',
    bar: 'bg-red-500',
    icon: 'AlertOctagon',
    message: 'Urgent intervention required. Immediate comprehensive STI screening and intensive counseling. PrEP evaluation mandatory. Emergency partner notification protocols. Follow-up within 1 week.',
  },
};

export function getRiskConfig(level) {
  return RISK_CONFIG[level] || RISK_CONFIG.moderate;
}