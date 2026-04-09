import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check } from 'lucide-react';
import { EmailServerForm } from '@/components/settings/EmailServerForm';
import { WebhookForm } from '@/components/settings/WebhookForm';
import { ModelConfigForm } from '@/components/settings/ModelConfigForm';

const steps = ['Email Source', 'Webhook Destinations', 'AI Model'];

export default function SettingsPage() {
  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<number[]>([]);

  const handleNext = (step: number) => {
    setCompletedSteps(prev => [...new Set([...prev, step])]);
    setCurrentStep(step + 1);
  };

  const goToStep = (i: number) => setCurrentStep(i);

  return (
    <div className="p-6 max-w-3xl mx-auto">
      {/* Stepper */}
      <div className="flex items-center justify-center mb-10">
        {steps.map((step, i) => (
          <div key={step} className="flex items-center">
            <div className="flex items-center gap-2 cursor-pointer" onClick={() => goToStep(i)}>
              <motion.div
                animate={{
                  backgroundColor: completedSteps.includes(i) ? 'hsl(160, 84%, 39%)' : currentStep === i ? 'hsl(239, 84%, 67%)' : 'transparent',
                  borderColor: completedSteps.includes(i) ? 'hsl(160, 84%, 39%)' : currentStep === i ? 'hsl(239, 84%, 67%)' : 'hsl(var(--border))',
                }}
                className="w-9 h-9 rounded-full border-2 flex items-center justify-center text-sm font-semibold"
              >
                {completedSteps.includes(i) ? (
                  <Check size={16} className="text-white" />
                ) : (
                  <span className={currentStep === i ? 'text-white' : 'text-muted-foreground'}>{i + 1}</span>
                )}
              </motion.div>
              <span className={`text-sm font-medium hidden sm:inline ${currentStep === i ? 'text-foreground' : 'text-muted-foreground'}`}>
                {step}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div className="w-12 sm:w-20 h-0.5 mx-3 bg-border relative overflow-hidden">
                <motion.div animate={{ scaleX: completedSteps.includes(i) ? 1 : 0 }} transition={{ duration: 0.4 }}
                  className="absolute inset-0 bg-success origin-left" />
              </div>
            )}
          </div>
        ))}
      </div>

      <AnimatePresence mode="wait">
        {currentStep === 0 && (
          <motion.div key="step0" initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} transition={{ duration: 0.3 }}>
            <EmailServerForm onNext={() => handleNext(0)} />
          </motion.div>
        )}
        {currentStep === 1 && (
          <motion.div key="step1" initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} transition={{ duration: 0.3 }}>
            <WebhookForm onBack={() => setCurrentStep(0)} onComplete={() => handleNext(1)} />
          </motion.div>
        )}
        {currentStep === 2 && (
          <motion.div key="step2" initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} transition={{ duration: 0.3 }}>
            <ModelConfigForm onBack={() => setCurrentStep(1)} onComplete={() => handleNext(2)} />
          </motion.div>
        )}
        {currentStep === 3 && (
          <motion.div key="done" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="text-center py-12">
            <div className="w-16 h-16 rounded-full bg-success/10 flex items-center justify-center mx-auto mb-4">
              <Check size={28} className="text-success" />
            </div>
            <h2 className="text-xl font-bold text-foreground mb-2">All settings saved</h2>
            <p className="text-muted-foreground text-sm mb-6">Your email source, webhooks, and AI model are configured.</p>
            <button onClick={() => setCurrentStep(0)} className="px-4 py-2 rounded-lg border border-border text-sm text-foreground hover:bg-muted transition-all">
              Review Settings
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
