import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Info, Loader2, CheckCircle, XCircle, Edit2, Mail, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { apiGetEmailConfig, apiSaveEmailConfig, apiTestEmailConnection } from '@/lib/api';

const schema = z.object({
  display_name: z.string().min(1, 'Required'),
  email: z.string().email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
  folder: z.string().optional(),
  poll_interval_minutes: z.coerce.number().optional(),
  mark_as_read: z.boolean().optional(),
});

type FormData = z.infer<typeof schema>;

const presets = [
  { name: 'Gmail',   color: 'bg-red-500',    hint: 'Requires App Password: Google Account → Security → 2-Step Verification → App Passwords' },
  { name: 'Outlook', color: 'bg-blue-500',   hint: 'Use your regular Outlook/Microsoft password' },
  { name: 'Yahoo',   color: 'bg-purple-500', hint: 'Requires App Password: Yahoo Account Security → Generate app password' },
  { name: 'Other',   color: 'bg-gray-400',   hint: 'IMAP settings will be auto-detected from your email domain' },
];

interface Props {
  onNext: () => void;
}

export function EmailServerForm({ onNext }: Props) {
  const [selectedPreset, setSelectedPreset] = useState<string>('');
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [polling, setPolling] = useState(false);
  const [testResult, setTestResult] = useState<'success' | 'error' | null>(null);
  const [testMessage, setTestMessage] = useState('');
  const [savedConfig, setSavedConfig] = useState<any>(null);
  const [editing, setEditing] = useState(false);

  const { register, handleSubmit, setValue, watch, formState: { errors, isValid } } = useForm<FormData>({
    resolver: zodResolver(schema),
    mode: 'onChange',
    defaultValues: { folder: 'INBOX', poll_interval_minutes: 1, mark_as_read: true },
  });

  useEffect(() => {
    apiGetEmailConfig().then((cfg: any) => {
      if (cfg?.email) {
        setSavedConfig(cfg);
        setValue('display_name', cfg.display_name || cfg.email);
        setValue('email', cfg.email);
        setValue('folder', cfg.folder || 'INBOX');
        setValue('poll_interval_minutes', cfg.poll_interval_minutes || 1);
        setValue('mark_as_read', cfg.mark_as_read ?? true);
        // Detect preset from imap_host
        if (cfg.imap_host?.includes('gmail')) setSelectedPreset('Gmail');
        else if (cfg.imap_host?.includes('office365') || cfg.imap_host?.includes('outlook')) setSelectedPreset('Outlook');
        else if (cfg.imap_host?.includes('yahoo')) setSelectedPreset('Yahoo');
        else setSelectedPreset('Other');
      }
    }).catch(() => {});
  }, []);

  const applyPreset = (name: string) => {
    setSelectedPreset(name);
    const emailVal = watch('email') || '';
    if (name === 'Gmail' && !emailVal.includes('@')) setValue('email', '@gmail.com');
    if (name === 'Outlook' && !emailVal.includes('@')) setValue('email', '@outlook.com');
    if (name === 'Yahoo' && !emailVal.includes('@')) setValue('email', '@yahoo.com');
  };

  const hint = presets.find(p => p.name === selectedPreset)?.hint || '';

  const handleTest = async (data: FormData) => {
    setSaving(true);
    try {
      await apiSaveEmailConfig({ email: data.email, password: data.password, display_name: data.display_name, folder: data.folder, poll_interval_minutes: data.poll_interval_minutes, mark_as_read: data.mark_as_read });
    } catch (e: any) { toast.error('Save failed: ' + e.message); setSaving(false); return; }
    setSaving(false);
    setTesting(true); setTestResult(null);
    try {
      const result: any = await apiTestEmailConnection();
      if (result.success) {
        setTestResult('success'); setTestMessage(result.message || 'Connection successful');
        toast.success('Connection successful!');
      } else {
        setTestResult('error'); setTestMessage(result.message || 'Connection failed');
        toast.error('Connection failed: ' + result.message);
      }
    } catch (e: any) { setTestResult('error'); setTestMessage(e.message); }
    setTesting(false);
  };

  const handlePollNow = async () => {
    setPolling(true);
    try {
      const res: any = await fetch('/api/settings/email/poll-now', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
      }).then(r => r.json());
      toast.success(`Polled: ${res.new_jobs_queued} new invoice(s) queued`);
    } catch (e: any) { toast.error(e.message); }
    setPolling(false);
  };

  const onSubmit = async (data: FormData) => {
    setSaving(true);
    try {
      const result: any = await apiSaveEmailConfig({ email: data.email, password: data.password, display_name: data.display_name, folder: data.folder, poll_interval_minutes: data.poll_interval_minutes, mark_as_read: data.mark_as_read });
      setSavedConfig({ email: data.email, display_name: data.display_name, imap_host: result.imap_host, imap_port: result.imap_port });
      setEditing(false);
      toast.success('Email source saved');
      onNext();
    } catch (e: any) { toast.error('Failed to save: ' + e.message); }
    setSaving(false);
  };

  const inputClass = 'w-full rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition-all';
  const labelClass = 'block text-sm font-medium text-foreground mb-1.5';

  // Saved config card
  if (savedConfig?.email && !editing) {
    return (
      <div>
        <div className="mb-6 flex items-start justify-between">
          <div>
            <h2 className="text-xl font-bold text-foreground">Email Source</h2>
            <p className="text-muted-foreground text-sm mt-1">Your email source is configured and polling automatically.</p>
          </div>
          <div className="flex gap-2">
            <button onClick={handlePollNow} disabled={polling}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-sm font-medium text-foreground hover:bg-muted transition-all disabled:opacity-50">
              {polling ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Poll Now
            </button>
            <button onClick={() => setEditing(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-sm font-medium text-foreground hover:bg-muted transition-all">
              <Edit2 size={13} /> Edit
            </button>
          </div>
        </div>

        <div className="border border-success/30 bg-success/5 rounded-xl p-5">
          <div className="flex items-center gap-2 text-success text-sm font-semibold mb-4">
            <CheckCircle size={16} /> Email source configured
          </div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
              <Mail size={18} className="text-primary" />
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">{savedConfig.display_name || savedConfig.email}</p>
              <p className="text-xs text-muted-foreground">{savedConfig.email}</p>
              {savedConfig.imap_host && <p className="text-xs text-muted-foreground">IMAP: {savedConfig.imap_host}:{savedConfig.imap_port}</p>}
            </div>
          </div>
        </div>

        <div className="flex justify-end mt-6">
          <button onClick={onNext} className="px-6 h-10 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary-dark transition-all">
            Next Step →
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold text-foreground">Email Source Configuration</h2>
          <p className="text-muted-foreground text-sm mt-1">Connect your inbox to automatically fetch and process invoice emails.</p>
        </div>
        {savedConfig?.email && <button onClick={() => setEditing(false)} className="text-sm text-muted-foreground hover:text-foreground">Cancel</button>}
      </div>

      {/* Provider presets */}
      <div className="flex gap-2 mb-6">
        {presets.map(p => (
          <button key={p.name} type="button" onClick={() => applyPreset(p.name)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm font-medium transition-all active:scale-[0.97] ${selectedPreset === p.name ? 'border-primary bg-primary/10 text-primary' : 'border-border text-foreground hover:bg-muted'}`}>
            <div className={`w-3 h-3 rounded-full ${p.color}`} />
            {p.name}
          </button>
        ))}
      </div>

      {hint && (
        <motion.div initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }}
          className="mb-4 p-3 rounded-lg bg-warning/10 border border-warning/20 text-warning text-sm flex gap-2">
          <Info size={16} className="mt-0.5 flex-shrink-0" />
          {hint}
        </motion.div>
      )}

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className={labelClass}>Display Name</label>
            <input {...register('display_name')} placeholder="e.g. Invoice Inbox" className={inputClass} />
            {errors.display_name && <p className="text-destructive text-xs mt-1">{errors.display_name.message}</p>}
          </div>
          <div>
            <label className={labelClass}>Email Address</label>
            <input {...register('email')} type="email" placeholder="invoices@company.com" className={inputClass} />
            {errors.email && <p className="text-destructive text-xs mt-1">{errors.email.message}</p>}
          </div>
        </div>

        <div>
          <label className={labelClass}>Password / App Password</label>
          <input {...register('password')} type="password" placeholder="Your password or app-specific password" className={inputClass} />
          {errors.password && <p className="text-destructive text-xs mt-1">{errors.password.message}</p>}
        </div>

        {/* Optional settings */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className={labelClass}>Folder to Monitor</label>
            <input {...register('folder')} placeholder="INBOX" className={inputClass} />
          </div>
          <div>
            <label className={labelClass}>Poll Interval (minutes)</label>
            <select {...register('poll_interval_minutes')} className={inputClass}>
              <option value={1}>Every 1 minute</option>
              <option value={5}>Every 5 minutes</option>
              <option value={15}>Every 15 minutes</option>
              <option value={30}>Every 30 minutes</option>
            </select>
          </div>
        </div>

        {/* <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
          <input {...register('mark_as_read')} type="checkbox" className="accent-primary w-4 h-4" />
          Mark emails as read after processing
        </label> */}

        {/* Test result */}
        {testResult === 'success' && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="p-3 rounded-lg bg-success/10 border border-success/20 text-success text-sm flex items-center gap-2">
            <CheckCircle size={14} /> {testMessage}
          </motion.div>
        )}
        {testResult === 'error' && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm flex items-center gap-2">
            <XCircle size={14} /> {testMessage}
          </motion.div>
        )}

        <div className="flex items-center justify-between pt-2">
          <button type="button" onClick={handleSubmit(handleTest)} disabled={!isValid || testing || saving}
            className="px-4 h-10 rounded-lg border border-border text-sm font-medium text-foreground hover:bg-muted transition-all flex items-center gap-2 disabled:opacity-50">
            {testing || saving ? <Loader2 size={14} className="animate-spin" /> : null}
            {saving ? 'Saving...' : testing ? 'Testing...' : 'Test Connection'}
          </button>
          <button type="submit" disabled={!isValid || saving}
            className="px-6 h-10 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary-dark transition-all active:scale-[0.97] disabled:opacity-50 flex items-center gap-2">
            {saving && <Loader2 size={14} className="animate-spin" />}
            Save & Continue →
          </button>
        </div>
      </form>
    </div>
  );
}
