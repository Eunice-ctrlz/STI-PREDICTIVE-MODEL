import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export function formatDate(date) {
  if (!date) return '—';
  const parsed = new Date(date);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function formatDateTime(date) {
  if (!date) return '—';
  const parsed = new Date(date);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatNumber(num) {
  if (num === null || num === undefined) return '—';
  return new Intl.NumberFormat('en-US').format(num);
}

export function formatPercent(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

/** Backend Patient.age_group keys → human labels. */
export const AGE_GROUP_LABELS = {
  under_15: 'Under 15',
  '15_24': '15–24',
  '25_34': '25–34',
  '35_44': '35–44',
  '45_plus': '45+',
};

export function formatAgeGroup(key) {
  return AGE_GROUP_LABELS[key] || key;
}

/** Patient.gender is stored as a single character. */
export const GENDER_LABELS = { M: 'Male', F: 'Female', O: 'Other', U: 'Unknown' };

export function formatGender(code) {
  return GENDER_LABELS[code] || code || '—';
}

export const RISK_CONFIG = {
  low: {
    label: 'Low Risk',
    color: 'emerald',
    hex: '#10b981',
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    bar: 'bg-emerald-500',
    badge: 'badge-green',
    icon: 'Shield',
    message: 'Continue routine screening per guidelines. Reinforce safer sex practices. Annual rescreening recommended.',
  },
  moderate: {
    label: 'Moderate Risk',
    color: 'amber',
    hex: '#f59e0b',
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
    bar: 'bg-amber-500',
    badge: 'badge-yellow',
    icon: 'AlertTriangle',
    message: 'Routine STI screening recommended. Provide condom counseling and risk reduction education. Schedule follow-up in 3 months.',
  },
  high: {
    label: 'High Risk',
    color: 'orange',
    hex: '#f97316',
    bg: 'bg-orange-50',
    text: 'text-orange-700',
    border: 'border-orange-200',
    bar: 'bg-orange-500',
    badge: 'badge-orange',
    icon: 'AlertTriangle',
    message: 'Immediate comprehensive STI screening recommended. Provide risk reduction counseling. Consider PrEP evaluation for HIV. Partner notification and contact tracing. Follow-up in 2-4 weeks.',
  },
  very_high: {
    label: 'Very High Risk',
    color: 'red',
    hex: '#ef4444',
    bg: 'bg-red-50',
    text: 'text-red-700',
    border: 'border-red-200',
    bar: 'bg-red-500',
    badge: 'badge-red',
    icon: 'AlertOctagon',
    message: 'Urgent intervention required. Immediate comprehensive STI screening and intensive counseling. PrEP evaluation mandatory. Emergency partner notification protocols. Follow-up within 1 week.',
  },
};

export function getRiskConfig(level) {
  return RISK_CONFIG[level] || RISK_CONFIG.moderate;
}

export const RISK_COLORS = Object.fromEntries(
  Object.entries(RISK_CONFIG).map(([key, cfg]) => [key, cfg.hex])
);

/** Title-case a snake_case key, e.g. very_high → Very High. */
export function humanize(key) {
  if (!key) return '';
  return String(key)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Turn an array of objects into a CSV file and trigger a download.
 * Used by the Reports page so "Export" produces a real artifact.
 */
export function downloadCsv(filename, rows) {
  if (!rows || rows.length === 0) return false;

  const headers = Object.keys(rows[0]);
  const escape = (value) => {
    if (value === null || value === undefined) return '';
    const str = String(value);
    return /[",\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str;
  };

  const csv = [
    headers.join(','),
    ...rows.map((row) => headers.map((h) => escape(row[h])).join(',')),
  ].join('\n');

  // Prepend a BOM so Excel reads UTF-8 correctly.
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  return true;
}
