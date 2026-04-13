import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Loader2, RotateCcw, CheckCircle, Info, Server } from 'lucide-react';
import { toast } from 'sonner';
import { apiGetModelConfig, apiSaveModelConfig, apiResetModelConfig } from '@/lib/api';

const PRESET_MODELS = [
  { label: 'System Default (from server config)', value: '', needsKey: false, needsUrl: false, isDefault: true },
  { label: 'Groq llama-3.3-70b (fast, free)', value: 'groq/llama-3.3-70b-versatile', needsKey: true, needsUrl: false },
  { label: 'Gemini 2.0 Flash', value: 'gemini/gemini-2.0-flash', needsKey: true, needsUrl: false },
  { label: 'OpenAI GPT-4o Mini', value: 'openai/gpt-4o-mini', needsKey: true, needsUrl: false },
  { label: 'Ollama (custom server)', value: 'ollama/custom', needsKey: false, needsUrl: true },
  { label: 'Custom model', value: 'custom', needsKey: true, needsUrl: true },
];

interface Props {
  onBack: () => void;
  onComplete: () => void;
}

export function ModelConfigForm({ onBack, onComplete }: Props) {
  const [config, setConfig] = useState<any>(null);
  const [selectedPreset, setSelectedPreset] = useState('');
  const [modelName, setModelName] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    apiGetModelConfig().then((cfg: any) => {
      setConfig(cfg);
      if (cfg.model_name) {
        // Match to a known preset
        const knownPreset = PRESET_MODELS.find(p => !p.isDefault && p.value !== 'custom' && p.value !== 'ollama/custom' && p.value === cfg.model_name);
        if (knownPreset) {
          setSelectedPreset(knownPreset.value);
        } else if (cfg.model_name.startsWith('ollama/')) {
          setSelectedPreset('ollama/custom');
          setModelName(cfg.model_name);
        } else {
          setSelectedPreset('custom');
          setModelName(cfg.model_name);
        }
        if (cfg.base_url) setBaseUrl(cfg.base_url);
        // Never pre-fill api_key — backend masks it as "***"
      } else {
        setSelectedPreset(''); // system default
      }
    }).catch(() => {});
  }, []);

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
        setConfig((c: any) => c ? { ...c, model_name: null, api_key: null, base_url: null } : c);
        toast.success('Using system default model');
        setEditing(false);
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
      setConfig((c: any) => ({ ...c, model_name: finalModel, effective_model: finalModel }));
      setEditing(false);
      toast.success('Model configuration saved');
      onComplete();
    } catch (e: any) { toast.error('Failed to save: ' + e.message); }
    setSaving(false);
  };

  const handleReset = async () => {
    setResetting(true);
    try {
      await apiResetModelConfig();
      setModelName(''); setApiKey(''); setBaseUrl('');
      setSelectedPreset('');
      setConfig((c: any) => c ? { ...c, model_name: null, api_key: null, base_url: null } : c);
      toast.success('Reset to system default');
    } catch (e: any) {
      toast.error(e.message);
    }
    setResetting(false);
  };

  const inputClass = 'w-full rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition-all';
  const labelClass = 'block text-sm font-medium text-foreground mb-1.5';

  // Saved state card
  if (config !== null && !editing) {
    return (
      <div>
        <div className="flex items-start justify-between mb-4">
          <p className="text-xs text-muted-foreground">Active model for invoice extraction.</p>
          <div className="flex gap-2">
            {config.model_name && (
              <button onClick={handleReset} disabled={resetting}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:bg-muted transition-all disabled:opacity-50">
                {resetting ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />} Reset
              </button>
            )}
            <button onClick={() => setEditing(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-muted transition-all">
              <span className="text-xs">✎</span> Edit
            </button>
          </div>
        </div>
        <div className="border border-border rounded-xl p-4 bg-surface-2">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
              <Server size={15} className="text-primary" />
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">{config.effective_model}</p>
              <p className="text-xs text-muted-foreground">
                {config.model_name ? 'Custom model' : 'System default'}
                {config.api_key ? ' · API key saved' : ''}
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex items-start justify-between">
        <p className="text-xs text-muted-foreground">Override the AI model for your account. Leave on system default if unsure.</p>
        {editing && <button onClick={() => setEditing(false)} className="text-xs text-muted-foreground hover:text-foreground">Cancel</button>}
      </div>

      {/* Current effective model info */}
      {config && (
        <div className="mb-4 p-3 rounded-lg bg-surface-2 border border-border text-sm text-muted-foreground flex items-center gap-2">
          <Server size={14} className="flex-shrink-0" />
          <span>Active: <strong className="text-foreground">{config.effective_model}</strong>
            {!config.model_name && <span className="ml-1 text-xs text-primary">(system default)</span>}
          </span>
        </div>
      )}

      <div className="space-y-4">
        <div>
          <label className={labelClass}>Model</label>
          <select value={selectedPreset} onChange={e => handlePresetChange(e.target.value)} className={inputClass}>
            {PRESET_MODELS.map(p => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>

        {isDefault && (
          <div className="p-3 rounded-lg bg-primary/5 border border-primary/20 text-xs text-muted-foreground flex items-start gap-2">
            <Info size={13} className="mt-0.5 flex-shrink-0 text-primary" />
            <span>The server's configured model will be used. No API key required from you.</span>
          </div>
        )}

        {selectedPreset === 'ollama/custom' && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="space-y-3">
            <div>
              <label className={labelClass}>Model Name</label>
              <input value={modelName} onChange={e => setModelName(e.target.value)} placeholder="e.g. ollama/llama3.1:8b" className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Ollama Base URL</label>
              <input value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="http://your-ollama-server:11434" className={inputClass} />
              <p className="text-xs text-muted-foreground mt-1">Leave blank to use the server's default Ollama URL</p>
            </div>
          </motion.div>
        )}

        {selectedPreset === 'custom' && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="space-y-3">
            <div>
              <label className={labelClass}>Model Name</label>
              <input value={modelName} onChange={e => setModelName(e.target.value)} placeholder="e.g. groq/mixtral-8x7b or openai/gpt-4o" className={inputClass} />
              <p className="text-xs text-muted-foreground mt-1">Format: provider/model-name</p>
            </div>
            <div>
              <label className={labelClass}>API Key</label>
              <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
                placeholder={config?.api_key ? 'Leave blank to keep existing key' : 'Your API key'} className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Base URL (optional)</label>
              <input value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="Only needed for self-hosted endpoints" className={inputClass} />
            </div>
          </motion.div>
        )}

        {preset?.needsKey && !preset?.needsUrl && selectedPreset !== 'custom' && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
            <label className={labelClass}>API Key</label>
            <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
              placeholder={config?.api_key ? 'Leave blank to keep existing key' : 'Your API key'} className={inputClass} />
            {config?.api_key && (
              <p className="text-xs text-success mt-1 flex items-center gap-1">
                <CheckCircle size={11} /> API key already saved
              </p>
            )}
          </motion.div>
        )}
      </div>

      <div className="flex items-center justify-between pt-6">
        <div className="flex gap-2">
          <button type="button" onClick={onBack}
            className="px-4 h-10 rounded-lg border border-border text-sm font-medium text-foreground hover:bg-muted transition-all">
            ← Back
          </button>
          {!isDefault && (
            <button type="button" onClick={handleReset} disabled={resetting}
              className="px-4 h-10 rounded-lg border border-border text-sm font-medium text-muted-foreground hover:bg-muted transition-all flex items-center gap-2 disabled:opacity-50">
              {resetting ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
              Use System Default
            </button>
          )}
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onComplete}
            className="px-4 h-10 rounded-lg border border-border text-sm font-medium text-muted-foreground hover:bg-muted transition-all">
            Skip
          </button>
          <button type="button" onClick={handleSave} disabled={saving || resetting}
            className="px-6 h-10 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary-dark transition-all active:scale-[0.97] disabled:opacity-50 flex items-center gap-2">
            {(saving || resetting) && <Loader2 size={14} className="animate-spin" />}
            {isDefault ? 'Use Default →' : 'Save & Finish →'}
          </button>
        </div>
      </div>
    </div>
  );
}
