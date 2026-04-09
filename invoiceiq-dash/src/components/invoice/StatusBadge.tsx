import { motion } from 'framer-motion';

interface Props {
  status: 'Pending' | 'Approved' | 'Rejected';
}

const statusConfig = {
  Pending: { bg: 'bg-warning/15', text: 'text-warning', dotClass: 'bg-warning animate-pulse' },
  Approved: { bg: 'bg-success/15', text: 'text-success', dotClass: 'bg-success' },
  Rejected: { bg: 'bg-destructive/15', text: 'text-destructive', dotClass: 'bg-destructive' },
};

export function StatusBadge({ status }: Props) {
  const config = statusConfig[status];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${config.bg} ${config.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${config.dotClass}`} />
      {status}
    </span>
  );
}
