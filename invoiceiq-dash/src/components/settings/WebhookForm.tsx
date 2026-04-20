import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Plus, Loader2, CheckCircle, Trash2, Edit2 } from 'lucide-react';
import { toast } from 'sonner';
import { apiCreateWebhook, apiGetWebhooks, apiDeleteWebhook, apiTestWebhook, apiTestWebhookPayload, apiUpdateWebhook } from '@/lib/api';

const webhookSchema = z.object({
  name: z.string().min(1, 'Required'),
  url: z.string().url('Must be a valid URL'),
});

type WebhookFormData = z.infer<typeof webhookSchema>;

type SavedWebhook = {
  id: string;
  name: string;
  url: string;
  is_active: boolean;
};

type WebhookTestResult = {
  success: boolean;
  status_code?: number;
  response?: string;
  message?: string;
};

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
  const [savedWebhooks, setSavedWebhooks] = useState<SavedWebhook[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const getErrorMessage = (error: unknown): string => {
    if (error instanceof Error && error.message) return error.message;
    return 'Something went wrong';
  };

  useEffect(() => {
    apiGetWebhooks().then((hooks: unknown) => {
      const normalized = Array.isArray(hooks) ? hooks as SavedWebhook[] : [];
      setSavedWebhooks(normalized);
      setShowForm(normalized.length === 0);
    }).catch(() => setShowForm(true));
  }, []);

  const { register, handleSubmit, watch, formState: { errors, isValid } } = useForm<WebhookFormData>({
    resolver: zodResolver(webhookSchema),
    mode: 'onChange',
  });

  const handleTest = async () => {
    setTesting(true);
    setTestResponse(null);
    try {
      const result = editingId
        ? await apiTestWebhook(editingId) as WebhookTestResult
        : await apiTestWebhookPayload({
            url: watch('url'),
            method: 'POST',
            timeout_seconds: 30,
          }) as WebhookTestResult;
      setTestResponse(result.success
        ? `HTTP ${result.status_code} OK\n\n${result.response}`
        : `Failed: ${result.message ?? 'Webhook test failed'}`);
      toast[result.success ? 'success' : 'error'](result.success ? 'Webhook test successful!' : (result.message ?? 'Webhook test failed'));
    } catch (e: unknown) {
      setTestResponse(`Error: ${getErrorMessage(e)}`);
    }
    setTesting(false);
  };

  const handleDelete = async (id: string) => {
    try {
      await apiDeleteWebhook(id);
      setSavedWebhooks(prev => prev.filter(w => w.id !== id));
      toast.success('Webhook deleted');
    } catch (e: unknown) {
      toast.error(getErrorMessage(e));
    }
  };

  const onSubmit = async (data: WebhookFormData) => {
    try {
      const payload = {
        name: data.name,
        url: data.url,
        method: 'POST',
        auth_type: 'None',
        content_type: 'application/json',
        payload_template: defaultPayload,
        retry_enabled: false,
        retry_attempts: 3,
        timeout_seconds: 30,
        is_active: true,
      };
      if (editingId) {
        await apiUpdateWebhook(editingId, payload);
        toast.success('Webhook updated');
      } else {
        await apiCreateWebhook(payload);
        toast.success('Webhook saved');
      }
      const hooks = await apiGetWebhooks();
      setSavedWebhooks(Array.isArray(hooks) ? hooks as SavedWebhook[] : []);
      setShowForm(false);
      setEditingId(null);
    } catch (e: unknown) {
      toast.error('Failed to save webhook: ' + getErrorMessage(e));
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
        </div>

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
