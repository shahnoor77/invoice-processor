import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Eye, EyeOff, Loader2, CheckCircle } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { apiRegister } from '@/lib/api';

const loginSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
  password: z.string().min(6, 'Password must be at least 6 characters'),
  remember: z.boolean().optional(),
});

const registerSchema = z.object({
  name: z.string().min(2, 'Name must be at least 2 characters'),
  email: z.string().email('Please enter a valid email address'),
  password: z.string().min(6, 'Password must be at least 6 characters'),
});

type LoginForm = z.infer<typeof loginSchema>;
type RegisterForm = z.infer<typeof registerSchema>;

export default function LoginPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [showPassword, setShowPassword] = useState(false);
  const [success, setSuccess] = useState(false);
  const [loginError, setLoginError] = useState('');
  const { login, loading } = useAuth();
  const navigate = useNavigate();

  const { register, handleSubmit, formState: { errors }, reset } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '', remember: false },
  });

  const regForm = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
    defaultValues: { name: '', email: '', password: '' },
  });

  const onSubmit = async (data: LoginForm) => {
    setLoginError('');
    const ok = await login(data.email, data.password);
    if (ok) {
      setSuccess(true);
      setTimeout(() => navigate('/invoices'), 800);
    } else {
      setLoginError('Invalid email or password.');
    }
  };

  const onRegister = async (data: RegisterForm) => {
    setLoginError('');
    try {
      await apiRegister(data.email, data.password, data.name);
      // Auto-login after register
      const ok = await login(data.email, data.password);
      if (ok) {
        setSuccess(true);
        setTimeout(() => navigate('/invoices'), 800);
      }
    } catch (e: any) {
      setLoginError(e.message || 'Registration failed');
    }
  };

  const switchMode = (m: 'login' | 'register') => {
    setMode(m);
    setLoginError('');
    reset();
    regForm.reset();
  };

  const floatingShapes = Array.from({ length: 6 }, (_, i) => ({
    id: i,
    size: 40 + Math.random() * 80,
    x: Math.random() * 100,
    y: Math.random() * 100,
    duration: 10 + Math.random() * 15,
    delay: Math.random() * 5,
    borderRadius: Math.random() > 0.5 ? '50%' : '20%',
  }));

  return (
    <div className="flex min-h-screen">
      {/* Left panel */}
      <motion.div
        initial={{ x: -60, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.6, ease: 'easeOut' }}
        className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-gradient-to-br from-primary via-purple-600 to-blue-700 flex-col items-center justify-center p-12"
      >
        {floatingShapes.map(shape => (
          <motion.div
            key={shape.id}
            className="absolute opacity-10"
            style={{
              width: shape.size,
              height: shape.size,
              left: `${shape.x}%`,
              top: `${shape.y}%`,
              borderRadius: shape.borderRadius,
              background: 'white',
            }}
            animate={{
              y: [0, -30, 0, 20, 0],
              x: [0, 15, -15, 5, 0],
              rotate: [0, 90, 180, 270, 360],
            }}
            transition={{
              duration: shape.duration,
              repeat: Infinity,
              delay: shape.delay,
              ease: 'easeInOut',
            }}
          />
        ))}

        <div className="relative z-10 text-center">
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.5 }}
            className="text-5xl font-bold text-white mb-4"
          >
            InvoiceFlow
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            className="text-white/80 text-lg mb-10"
          >
            Intelligent invoice management for modern teams
          </motion.p>

          <div className="flex flex-row flex-wrap gap-3 items-center justify-center">
            {['AI-Powered Processing', 'Real-time Webhooks', 'Multi-server Email'].map((text, i) => (
              <motion.div
                key={text}
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.7 + i * 0.15 }}
                className="px-4 py-2 rounded-full bg-white/15 backdrop-blur-sm text-white text-sm font-medium"
              >
                {text}
              </motion.div>
            ))}
          </div>
        </div>
      </motion.div>

      {/* Right panel */}
      <motion.div
        initial={{ opacity: 0, x: 40 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.6, delay: 0.2, ease: 'easeOut' }}
        className="flex-1 flex items-center justify-center p-8 bg-background"
      >
        <div className="w-full max-w-md">
          <div className="mb-8">
            <div className="flex items-center gap-2 mb-6">
              <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
                <span className="text-primary-foreground font-bold text-sm">IF</span>
              </div>
              <span className="font-semibold text-foreground text-lg lg:hidden">InvoiceFlow</span>
            </div>
            <h2 className="text-2xl font-bold text-foreground">
              {mode === 'login' ? 'Sign in to InvoiceFlow' : 'Create your account'}
            </h2>
            <p className="text-muted-foreground mt-1">
              {mode === 'login' ? 'Welcome back. Enter your credentials to continue.' : 'Set up your account to start processing invoices.'}
            </p>
          </div>

          {/* Mode toggle */}
          <div className="flex gap-0.5 bg-surface-2 rounded-lg p-0.5 border border-border mb-6">
            {(['login', 'register'] as const).map(m => (
              <button key={m} type="button" onClick={() => switchMode(m)}
                className={`flex-1 py-2 rounded-md text-sm font-medium transition-all ${mode === m ? 'bg-background text-foreground shadow-sm border border-border' : 'text-muted-foreground hover:text-foreground'}`}>
                {m === 'login' ? 'Sign In' : 'Register'}
              </button>
            ))}
          </div>

          {mode === 'login' ? (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
              <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
                <label className="block text-sm font-medium text-foreground mb-1.5">Email</label>
                <input {...register('email')} type="email" placeholder="you@company.com"
                  className={`w-full rounded-lg border bg-surface-2 px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition-all ${errors.email ? 'border-destructive' : 'border-border'}`} />
                {errors.email && <p className="text-destructive text-xs mt-1">{errors.email.message}</p>}
              </motion.div>

              <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}>
                <label className="block text-sm font-medium text-foreground mb-1.5">Password</label>
                <div className="relative">
                  <input {...register('password')} type={showPassword ? 'text' : 'password'} placeholder="••••••••"
                    className={`w-full rounded-lg border bg-surface-2 px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition-all pr-10 ${errors.password ? 'border-destructive' : 'border-border'}`} />
                  <button type="button" onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors">
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                {errors.password && <p className="text-destructive text-xs mt-1">{errors.password.message}</p>}
              </motion.div>

              {loginError && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
                  {loginError}
                </motion.div>
              )}

              <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6 }}>
                <button type="submit" disabled={loading || success}
                  className={`w-full h-11 rounded-lg font-medium text-sm transition-all duration-150 flex items-center justify-center gap-2 ${success ? 'bg-success text-success-foreground' : 'bg-primary text-primary-foreground hover:bg-primary-dark active:scale-[0.97]'} disabled:opacity-70`}>
                  {success ? <><CheckCircle size={16} /> Signed in!</> : loading ? <><Loader2 size={16} className="animate-spin" /> Signing in…</> : 'Sign In'}
                </button>
              </motion.div>
            </form>
          ) : (
            <form onSubmit={regForm.handleSubmit(onRegister)} className="space-y-5">
              <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }}>
                <label className="block text-sm font-medium text-foreground mb-1.5">Full Name</label>
                <input {...regForm.register('name')} placeholder="Your name"
                  className={`w-full rounded-lg border bg-surface-2 px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition-all ${regForm.formState.errors.name ? 'border-destructive' : 'border-border'}`} />
                {regForm.formState.errors.name && <p className="text-destructive text-xs mt-1">{regForm.formState.errors.name.message}</p>}
              </motion.div>

              <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
                <label className="block text-sm font-medium text-foreground mb-1.5">Email</label>
                <input {...regForm.register('email')} type="email" placeholder="you@company.com"
                  className={`w-full rounded-lg border bg-surface-2 px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition-all ${regForm.formState.errors.email ? 'border-destructive' : 'border-border'}`} />
                {regForm.formState.errors.email && <p className="text-destructive text-xs mt-1">{regForm.formState.errors.email.message}</p>}
              </motion.div>

              <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
                <label className="block text-sm font-medium text-foreground mb-1.5">Password</label>
                <div className="relative">
                  <input {...regForm.register('password')} type={showPassword ? 'text' : 'password'} placeholder="Min 6 characters"
                    className={`w-full rounded-lg border bg-surface-2 px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition-all pr-10 ${regForm.formState.errors.password ? 'border-destructive' : 'border-border'}`} />
                  <button type="button" onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors">
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                {regForm.formState.errors.password && <p className="text-destructive text-xs mt-1">{regForm.formState.errors.password.message}</p>}
              </motion.div>

              {loginError && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
                  {loginError}
                </motion.div>
              )}

              <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
                <button type="submit" disabled={loading || success}
                  className={`w-full h-11 rounded-lg font-medium text-sm transition-all duration-150 flex items-center justify-center gap-2 ${success ? 'bg-success text-success-foreground' : 'bg-primary text-primary-foreground hover:bg-primary-dark active:scale-[0.97]'} disabled:opacity-70`}>
                  {success ? <><CheckCircle size={16} /> Account created!</> : loading ? <><Loader2 size={16} className="animate-spin" /> Creating account…</> : 'Create Account'}
                </button>
              </motion.div>
            </form>
          )}

          <p className="text-center text-xs text-muted-foreground mt-10">
            © 2025 InvoiceFlow. All rights reserved.
          </p>
        </div>
      </motion.div>
    </div>
  );
}
