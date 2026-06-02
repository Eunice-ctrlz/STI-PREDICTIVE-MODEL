
export const getRiskColor = (level: string): string => {
  switch (level?.toLowerCase()) {
    case 'low':      return 'bg-green-500';
    case 'moderate': return 'bg-yellow-500';
    case 'high':     return 'bg-orange-500';
    case 'critical': return 'bg-red-600';
    default:         return 'bg-gray-400';
  }
};

export const getRiskTextColor = (level: string): string => {
  switch (level?.toLowerCase()) {
    case 'low':      return 'text-green-600';
    case 'moderate': return 'text-yellow-600';
    case 'high':     return 'text-orange-600';
    case 'critical': return 'text-red-600';
    default:         return 'text-gray-500';
  }
};

// Icon components for each risk level
const LowIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const ModerateIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
  </svg>
);

const HighIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const CriticalIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
  </svg>
);

export const getRiskIcon = (level: string): React.FC<{ className?: string }> => {
  switch (level?.toLowerCase()) {
    case 'low':      return LowIcon;
    case 'moderate': return ModerateIcon;
    case 'high':     return HighIcon;
    case 'critical': return CriticalIcon;
    default:         return ModerateIcon;
  }
};