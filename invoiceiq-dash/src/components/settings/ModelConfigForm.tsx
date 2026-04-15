import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Loader2, RotateCcw, CheckCircle, Info, Server, Plus, Trash2, Zap } from 'lucide-react';
import { toast } from 'sonner';
import { apiGetModelConfig, apiSaveModelConfig, apiResetModelConfig } from '@/lib/api';

const PRESET_MODELS = [
  { label: 'System Default (from server config)', value: '', needsKey: false, needsUrl: false },
  { label: 'Groq llama-3.3-70b (fast, free)', value: 'groq/llama-3.3-70b-versatile', needsKey: true, needsUrl: false },
  { label: 'Gemini 2.0 Flash', value: 'gemini/gemini-2.0-flash', needsKey: true, needsUrl: false },
  { label: 'OpenAI GPT-4o Mini', value: 'openai/gpt-4o-mini', needsKey: true, needsUrl: false },
  { label: 'Ollama (custom server)', value: 'ollama/custom', needsKey: false, needsUrl: true },
  { label: 'Custom model', value: 'custom', needsKey: true, needsUrl: true },
];

interface SavedConfig {
  id: string;
  model_name: string | null;
  api_key: string | null;
  base_url: string | null;
  status: string;
}

interface Props {
  onBack: () => void;
  onComplete: () => void;
}

export function ModelConfigForm({ onBack, onComplete }: Props) {
  const [config, setConfig] = useState<any>(null);
  const [savedConfigs, setSavedConfigs] = useState<SavedConfig[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState('');
  const [modelName, setModelName] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [activating, setActivating] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = () => {
    apiGetModelConfig().then((cfg: any) => {
      setConfig(cfg);
      setSavedConfigs(cfg.configured_models || []);
    }).catch(() => {});
  };

  useEffect(() => { load(); }, []);

  const preset = PRESET_MODELS.find(p => p.value === selectedPreset);
  const isDefault = selectedPreset === '';

  const handlePresetChange = (value: string) => {
    setSelectedPreset(value);
    setModelName('');
    setApiKey('');
    setBaseUrl('');
  };

  const handleSave = async () => {
    if (isDefault) {
      setResetting(true);
      try {
        await apiResetModelConfig();
        toast.success('Reset to system default');
        load();
        setShowForm(false);
        onComplete();
      } catch (e: any) { toast.error(e.message); }
      setResetting(false);
      return;
    }
    setSaving(true);
    try {
      let finalModel = selectedPreset;
      if (selectedPreset === 'custom' || selectedPreset === 'ollama/custom') finalModel = modelName.trim();
      if (!finalModel) { toast.error('Please enter a model name'); setSaving(false); return; }
      await apiSaveModelConfig({ model_name: finalModel, api_key: apiKey.trim() || null, base_url: baseUrl.trim() || null });
      toast.success('Model saved and activated');
      load();
      setShowForm(false);
      setModelName(''); setApiKey(''); setBaseUrl(''); setSelectedPreset('');
      onComplete();
    } catch (e: any) { toast.error('Failed to save: ' + e.message); }
    setSaving(false);
  };

  const handleActivate = async (id: string) => {
    setActivating(id);
    try {
      await fetch(`/api/settings/model/${id}/activate`, {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
      });
      toast.success('Model activated');
      load();
    } catch (e: any) { toast.error(e.message); }
    setActivating(null);
  };

  const handleDelete = async (id: string) => {
    setDeleting(id);
    try {
      await fetch(`/api/settings/model/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
      });
      toast.success('Model config deleted');
      load();
    } catch (e: any) { toast.error(e.message); }
    setDeleting(null);
  };

  const inputClass = 'w-full rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition-all';
  const labelClass = 'block text-sm font-medium text-foreground mb-1.5';

  return (
    <div>
      <div className="mb-5">
        <h2 className="text-xl font-bold text-foreground">AI Model Configuration</h2>
        <p className="text-muted-foreground text-sm mt-1">
          Save multiple model configs and activate the one you want to use.
        </p>
      </div>

      {/* Active model banner */}
      {config && (
        <div className="mb-4 p-3 rounded-lg bg-surface-2 border border-border text-sm flex items-center gap-2">
          <Server size={14} className="flex-shrink-0 text-primary" />
          <span className="text-muted-foreground">Active: <strong className="text-foreground">{config.effective_model}</strong>
            {!config.active_model && <span className="ml-1 text-xs text-primary">(system default)</span>}
          </span>
        </div>
      )}

      {/* Saved configs list */}
      {savedConfigs.length > 0 && (
        <div className="mb-4 space-y-2">
          {savedConfigs.map(c => (
            <div key={c.id}
              className={`flex items-center justify-between p-3 rounded-lg border text-sm ${c.status === 'active' ? 'border-success/40 bg-success/5' : 'border-border bg-surface-2'}`}>
              <div className="flex items-center gap-2 min-w-0">
                {c.status === 'active' && <CheckCircle size={13} className="text-success flex-shrink-0" />}
                <div className="min-w-0">
                  <p className="text-xs font-medium text-foreground truncate">{c.model_name || 'System default'}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {c.status === 'active' ? 'Active' : 'Inactive'}
                    {c.api_key ? ' · key saved' : ''}
                    {c.base_url ? ` · ${c.base_url}` : ''}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                {c.status !== 'active' && (
                  <button onClick={() => handleActivate(c.id)} disabled={activating === c.id}
                    className="flex items-center gap-1 px-2 py-1 rounded-md border border-primary/30 text-[11px] font-medium text-primary hover:bg-primary/10 transition-all disabled:opacity-50">
                    {activating === c.id ? <Loader2 size={10} className="animate-spin" /> : <Zap size={10} />} Activate
                  </button>
                )}
                <button onClick={() => handleDelete(c.id)} disabled={deleting === c.id}
                  className="p-1.5 rounded-md border border-destructive/30 text-destructive hover:bg-destructive/10 transition-all disabled:opacity-50">
                  {deleting === c.id ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add new config form */}
      {showForm ? (
        <div className="border border-border rounded-xl p-4 space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-foreground">Add Model Config</p>
            <button onClick={() => setShowForm(false)} className="text-xs text-muted-foreground hover:text-foreground">Cancel</button>
          </div>

          <div>
            <label className={labelClass}>Model</label>
            <select value={selectedPreset} onChange={e => handlePresetChange(e.target.value)} className={inputClass}>
              {PRESET_MODELS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </div>

          {isDefault && (
            <div className="p-3 rounded-lg bg-primary/5 border border-primary/20 text-xs text-muted-foreground flex items-start gap-2">
              <Info size={13} className="mt-0.5 flex-shrink-0 text-primary" />
              <span>Will reset to server's configured model. No API key required.</span>
            </div>
          )}

          {selectedPreset === 'ollama/custom' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-3">
              <div>
                <label className={labelClass}>Model Name</label>
                <input value={modelName} onChange={e => setModelName(e.target.value)} placeholder="e.g. ollama/llama3.1:8b" className={inputClass} />
              </div>
              <div>
                <label className={labelClass}>Ollama Base URL</label>
                <input value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="http://your-ollama-server:11434" className={inputClass} />
              </div>
            </motion.div>
          )}

          {selectedPreset === 'custom' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-3">
              <div>
                <label className={labelClass}>Model Name</label>
                <input value={modelName} onChange={e => setModelName(e.target.value)} placeholder="e.g. groq/mixtral-8x7b" className={inputClass} />
              </div>
              <div>
                <label className={labelClass}>API Key</label>
                <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="Your API key" className={inputClass} />
              </div>
              <div>
                <label className={labelClass}>Base URL (optional)</label>
                <input value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="Only for self-hosted endpoints" className={inputClass} />
              </div>
            </motion.div>
          )}

          {preset?.needsKey && !preset?.needsUrl && selectedPreset !== 'custom' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <label className={labelClass}>API Key</label>
              <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="Your API key" className={inputClass} />
            </motion.div>
          )}

          <button onClick={handleSave} disabled={saving || resetting}
            className="w-full h-9 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary-dark transition-all disabled:opacity-50 flex items-center justify-center gap-2">
            {(saving || resetting) && <Loader2 size={13} className="animate-spin" />}
            Save & Activate
          </button>
        </div>
      ) : (
        <button onClick={() => setShowForm(true)}
          className="w-full h-9 rounded-lg border border-dashed border-border text-sm text-muted-foreground hover:border-primary hover:text-primary transition-all flex items-center justify-center gap-2">
          <Plus size={14} /> Add Model Config
        </button>
      )}

      <div className="flex items-center justify-between pt-6">
        <div className="flex gap-2">
          <button type="button" onClick={onBack}
            className="px-4 h-10 rounded-lg border border-border text-sm font-medium text-foreground hover:bg-muted transition-all">
            ← Back
          </button>
          <button type="button" onClick={() => { apiResetModelConfig().then(() => { toast.success('Reset to system default'); load(); }).catch(e => toast.error(e.message)); }}
            className="px-4 h-10 rounded-lg border border-border text-sm font-medium text-muted-foreground hover:bg-muted transition-all flex items-center gap-2">
            <RotateCcw size={13} /> Use System Default
          </button>
        </div>
        <button type="button" onClick={onComplete}
          className="px-6 h-10 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary-dark transition-all">
          Finish →
        </button>
      </div>
    </div>
  );
}
