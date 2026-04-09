import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';

export function SuccessAnimation() {
  const navigate = useNavigate();

  useEffect(() => {
    const timer = setTimeout(() => navigate('/invoices'), 2500);
    return () => clearTimeout(timer);
  }, [navigate]);

  return (
    <div className="fixed inset-0 z-50 bg-background flex flex-col items-center justify-center">
      {/* Checkmark */}
      <motion.svg
        width="100"
        height="100"
        viewBox="0 0 100 100"
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ type: 'spring', stiffness: 200, damping: 15 }}
      >
        <motion.circle
          cx="50"
          cy="50"
          r="45"
          fill="none"
          stroke="hsl(160, 84%, 39%)"
          strokeWidth="4"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.6, delay: 0.2 }}
        />
        <motion.path
          d="M30 52 L44 66 L70 38"
          fill="none"
          stroke="hsl(160, 84%, 39%)"
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.4, delay: 0.6 }}
        />
      </motion.svg>

      {/* Confetti particles */}
      {Array.from({ length: 20 }).map((_, i) => (
        <motion.div
          key={i}
          className="absolute w-2 h-2 rounded-full"
          style={{
            background: ['hsl(239,84%,67%)', 'hsl(160,84%,39%)', 'hsl(38,92%,50%)', 'hsl(0,84%,60%)'][i % 4],
          }}
          initial={{ x: 0, y: 0, opacity: 1, scale: 0 }}
          animate={{
            x: (Math.random() - 0.5) * 400,
            y: (Math.random() - 0.5) * 400,
            opacity: 0,
            scale: [0, 1.5, 0],
          }}
          transition={{ duration: 1.5, delay: 0.4 + Math.random() * 0.3 }}
        />
      ))}

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 1 }}
        className="mt-8 text-center"
      >
        <h2 className="text-2xl font-bold text-foreground">Setup Complete!</h2>
        <p className="text-muted-foreground mt-2">Redirecting to Invoice Dashboard…</p>
      </motion.div>
    </div>
  );
}
