import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useForm, useFieldArray } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Plus, X, Loader2, CheckCircle, Trash2, Edit2 } from 'lucide-react';
import { toast } from 'sonner';
import { apiCreateWebhook, apiGetWebhooks, apiDeleteWebhook, apiTestWebhook, apiUpdateWebhook } from '@/lib/api';

const webhookSchema = z.object({
  name: z.string().min(1, 'Required'),
  url: z.string().url('Must be a valid URL'),
  method: z.string(),
  authType: z.string(),
  bearerToken: z.string().optional(),
  apiKeyName: z.string().optional(),
  apiKeyValue: z.string().optional(),
  basicUser: z.string().optional(),
  basicPass: z.string().optional(),
  hmacSecret: z.string().optional(),
  hmacAlgo: z.string().optional(),
  contentType: z.string(),
  retryEnabled: z.boolean(),
  retryAttempts: z.coerce.number().optional(),
  retryDelay: z.string().optional(),
  headers: z.array(z.object({ key: z.string(), value: z.string() })),
  payload: z.string().optional(),
  timeout: z.coerce.number(),
  active: z.boolean(),
});

type WebhookFormData = z.infer<typeof webhookSchema>;

interface Props {
  onBack: () => void;
  onComplete: () => void;
}

const defaultPayload = `{
  "invoice_id": "{{invoice.id}}",
  "vendor": "{{invoice.vendor}}",
  "amount": "{{invoice.total}}",
  "status": "{{invoice.status}}"
}`;

export function WebhookForm({ onBack, onComplete }: Props) {
  const [testing, setTesting] = useState(false);
  const [testResponse, setTestResponse] = useState<string | null>(null);
  const [savedWebhooks, setSavedWebhooks] = useState<any[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    apiGetWebhooks().then((hooks: any) => {
      setSavedWebhooks(Array.isArray(hooks) ? hooks : []);
      setShowForm(hooks.length === 0);
    }).catch(() => setShowForm(true));
  }, []);

  const { register, handleSubmit, watch, control, formState: { errors, isValid } } = useForm<WebhookFormData>({
    resolver: zodResolver(webhookSchema),
    mode: 'onChange',
    defaultValues: {
      method: 'POST',
      authType: 'None',
      contentType: 'application/json',
      retryEnabled: false,
      retryAttempts: 3,
      retryDelay: '30s',
      headers: [],
      payload: defaultPayload,
      timeout: 30,
      active: true,
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: 'headers' });

  const authType = watch('authType');
  const retryEnabled = watch('retryEnabled');

  const handleTest = async () => {
    setTesting(true);
    setTestResponse(null);
    // Save first then test
    const data = { name: 'test', url: watch('url'), method: 'POST', is_active: true };
    try {
      const created: any = await apiCreateWebhook(data);
      const result: any = await apiTestWebhook(created.id);
      setTestResponse(result.success
        ? `HTTP ${result.status_code} OK\n\n${result.response}`
        : `Failed: ${result.message}`);
      toast[result.success ? 'success' : 'error'](result.success ? 'Webhook test successful!' : result.message);
    } catch (e: any) {
      setTestResponse(`Error: ${e.message}`);
    }
    setTesting(false);
  };

  const handleDelete = async (id: string) => {
    try {
      await apiDeleteWebhook(id);
      setSavedWebhooks(prev => prev.filter(w => w.id !== id));
      toast.success('Webhook deleted');
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  const onSubmit = async (data: WebhookFormData) => {
    try {
      const payload = {
        name: data.name, url: data.url, method: data.method,
        auth_type: data.authType, content_type: data.contentType,
        payload_template: data.payload, retry_enabled: data.retryEnabled,
        retry_attempts: data.retryAttempts, timeout_seconds: data.timeout,
        is_active: data.active,
      };
      if (editingId) {
        await apiUpdateWebhook(editingId, payload);
        toast.success('Webhook updated');
      } else {
        await apiCreateWebhook(payload);
        toast.success('Webhook saved');
      }
      const hooks: any = await apiGetWebhooks();
      setSavedWebhooks(Array.isArray(hooks) ? hooks : []);
      setShowForm(false);
      setEditingId(null);
    } catch (e: any) {
      toast.error('Failed to save webhook: ' + e.message);
    }
  };

  const inputClass = 'w-full rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition-all';
  const labelClass = 'block text-sm font-medium text-foreground mb-1.5';

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-bold text-foreground">Webhook & Integration Setup</h2>
        <p className="text-muted-foreground text-sm mt-1">Configure the destination endpoint where approved invoice data will be delivered. <span className="text-warning font-medium">Optional</span> — you can skip this and configure later. Invoices will stay in PENDING state until approved.</p>
      </div>

      {/* Saved webhooks list */}
      {savedWebhooks.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-foreground">Configured Webhooks</h3>
            <button type="button" onClick={() => { setShowForm(true); setEditingId(null); }}
              className="text-xs text-primary hover:text-primary-dark flex items-center gap-1">
              <Plus size={12} /> Add New
            </button>
          </div>
          <div className="space-y-2">
            {savedWebhooks.map(w => (
              <div key={w.id} className="flex items-center justify-between p-3 rounded-lg border border-border bg-surface-2">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">{w.name}</p>
                  <p className="text-xs text-muted-foreground truncate">{w.url}</p>
                </div>
                <div className="flex items-center gap-2 ml-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${w.is_active ? 'bg-success/10 text-success' : 'bg-muted text-muted-foreground'}`}>
                    {w.is_active ? 'Active' : 'Inactive'}
                  </span>
                  <button type="button" onClick={() => { setEditingId(w.id); setShowForm(true); }}
                    className="p-1.5 text-muted-foreground hover:text-foreground transition-colors">
                    <Edit2 size={13} />
                  </button>
                  <button type="button" onClick={() => handleDelete(w.id)}
                    className="p-1.5 text-muted-foreground hover:text-destructive transition-colors">
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!showForm && savedWebhooks.length > 0 && (
        <div className="flex justify-between pt-4">
          <button type="button" onClick={onBack} className="px-4 h-10 rounded-lg border border-border text-sm font-medium text-foreground hover:bg-muted transition-all">← Back</button>
          <button type="button" onClick={onComplete} className="px-6 h-10 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary-dark transition-all">Next Step →</button>
        </div>
      )}

      {showForm && (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className={labelClass}>Webhook Name</label>
            <input {...register('name')} placeholder="e.g. Google Sheets Integration" className={inputClass} />
            {errors.name && <p className="text-destructive text-xs mt-1">{errors.name.message}</p>}
          </div>
          <div>
            <label className={labelClass}>Endpoint URL</label>
            <input {...register('url')} placeholder="https://your-endpoint.com/webhook" className={inputClass} />
            {errors.url && <p className="text-destructive text-xs mt-1">{errors.url.message}</p>}
          </div>
          <div>
            <label className={labelClass}>HTTP Method</label>
            <select {...register('method')} className={inputClass}>
              <option>POST</option><option>PUT</option><option>PATCH</option>
            </select>
          </div>
          <div>
            <label className={labelClass}>Authentication Type</label>
            <select {...register('authType')} className={inputClass}>
              <option>None</option><option>Bearer Token</option><option>API Key</option><option>Basic Auth</option><option>HMAC Secret</option>
            </select>
          </div>
        </div>

        {/* Conditional auth fields */}
        <AnimatePresence mode="wait">
          {authType === 'Bearer Token' && (
            <motion.div key="bearer" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
              <label className={labelClass}>Bearer Token</label>
              <input {...register('bearerToken')} type="password" className={inputClass} />
            </motion.div>
          )}
          {authType === 'API Key' && (
            <motion.div key="apikey" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="grid grid-cols-2 gap-4">
              <div><label className={labelClass}>Key Name</label><input {...register('apiKeyName')} className={inputClass} /></div>
              <div><label className={labelClass}>Key Value</label><input {...register('apiKeyValue')} type="password" className={inputClass} /></div>
            </motion.div>
          )}
          {authType === 'Basic Auth' && (
            <motion.div key="basic" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="grid grid-cols-2 gap-4">
              <div><label className={labelClass}>Username</label><input {...register('basicUser')} className={inputClass} /></div>
              <div><label className={labelClass}>Password</label><input {...register('basicPass')} type="password" className={inputClass} /></div>
            </motion.div>
          )}
          {authType === 'HMAC Secret' && (
            <motion.div key="hmac" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="grid grid-cols-2 gap-4">
              <div><label className={labelClass}>Secret Key</label><input {...register('hmacSecret')} type="password" className={inputClass} /></div>
              <div><label className={labelClass}>Algorithm</label>
                <select {...register('hmacAlgo')} className={inputClass}><option>SHA256</option><option>SHA512</option></select>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className={labelClass}>Content Type</label>
            <select {...register('contentType')} className={inputClass}>
              <option>application/json</option><option>application/x-www-form-urlencoded</option><option>multipart/form-data</option>
            </select>
          </div>
          <div>
            <label className={labelClass}>Timeout (seconds)</label>
            <input {...register('timeout')} type="number" className={inputClass} />
          </div>
        </div>

        {/* Retry */}
        <div className="space-y-3">
          <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
            <input {...register('retryEnabled')} type="checkbox" className="accent-primary w-4 h-4" />
            Retry on Failure
          </label>
          {retryEnabled && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="grid grid-cols-2 gap-4">
              <div><label className={labelClass}>Retry Attempts</label><input {...register('retryAttempts')} type="number" className={inputClass} /></div>
              <div><label className={labelClass}>Retry Delay</label>
                <select {...register('retryDelay')} className={inputClass}><option>30s</option><option>1min</option><option>5min</option><option>Exponential</option></select>
              </div>
            </motion.div>
          )}
        </div>

        {/* Custom Headers */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className={labelClass}>Custom Headers</label>
            <button type="button" onClick={() => append({ key: '', value: '' })} className="text-primary text-sm font-medium flex items-center gap-1 hover:text-primary-dark transition-colors">
              <Plus size={14} /> Add Header
            </button>
          </div>
          <AnimatePresence>
            {fields.map((field, i) => (
              <motion.div
                key={field.id}
                layout
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="flex gap-2 mb-2"
              >
                <input {...register(`headers.${i}.key`)} placeholder="Key" className={inputClass} />
                <input {...register(`headers.${i}.value`)} placeholder="Value" className={inputClass} />
                <button type="button" onClick={() => remove(i)} className="px-2 text-muted-foreground hover:text-destructive transition-colors">
                  <X size={16} />
                </button>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>

        {/* Payload */}
        <div>
          <label className={labelClass}>Payload Template</label>
          <textarea {...register('payload')} rows={8} className={`${inputClass} font-mono text-xs`} />
        </div>

        {/* Active toggle */}
        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
          <input {...register('active')} type="checkbox" className="accent-primary w-4 h-4" />
          Active — Enable this webhook
        </label>

        {/* Test */}
        <div>
          <button type="button" onClick={handleTest} disabled={testing} className="px-4 h-10 rounded-lg border border-border text-sm font-medium text-foreground hover:bg-muted transition-all flex items-center gap-2 disabled:opacity-50">
            {testing ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle size={14} />}
            Test Webhook
          </button>
          {testResponse && (
            <motion.pre initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="mt-3 p-3 rounded-lg bg-surface-3 border border-border text-xs font-mono text-foreground overflow-auto">
              {testResponse}
            </motion.pre>
          )}
        </div>

        {/* Navigation */}
        <div className="flex justify-between pt-4">
          <button type="button" onClick={onBack} className="px-4 h-10 rounded-lg border border-border text-sm font-medium text-foreground hover:bg-muted transition-all">
            ← Back
          </button>
          <div className="flex gap-2">
            <button type="button" onClick={onComplete}
              className="px-4 h-10 rounded-lg border border-border text-sm font-medium text-muted-foreground hover:bg-muted transition-all">
              Skip for now
            </button>
            <button type="submit" disabled={!isValid} className="px-6 h-10 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary-dark transition-all active:scale-[0.97] disabled:opacity-50">
              Save & Complete →
            </button>
          </div>
        </div>
      </form>
      )}
    </div>
  );
}
