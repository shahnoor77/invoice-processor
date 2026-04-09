import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Loader2, RotateCcw, CheckCircle, Info } from 'lucide-react';
import { toast } from 'sonner';
import { apiGetModelConfig, apiSaveModelConfig, apiResetModelConfig } from '@/lib/api';

const PRESET_MODELS = [
  { label: 'Ollama qwen3.5:9b (default)', value: 'ollama/qwen3.5:9b', needsKey: false, needsUrl: true },
  { label: 'Ollama llama3.1:8b', value: 'ollama/llama3.1:8b', needsKey: false, needsUrl: true },
  { label: 'Groq llama-3.3-70b', value: 'groq/llama-3.3-70b-versatile', needsKey: true, needsUrl: false },
  { label: 'Gemini 2.0 Flash', value: 'gemini/gemini-2.0-flash', needsKey: true, needsUrl: false },
  { label: 'OpenAI GPT-4o Mini', value: 'openai/gpt-4o-mini', needsKey: true, needsUrl: false },
  { label: 'Custom', value: 'custom', needsKey: true, needsUrl: true },
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

  useEffect(() => {
    apiGetModelConfig().then((cfg: any) => {
      setConfig(cfg);
      if (cfg.model_name) {
        setModelName(cfg.model_name);
        const preset = PRESET_MODELS.find(p => p.value === cfg.model_name);
        setSelectedPreset(preset ? preset.value : 'custom');
      } else {
        setSelectedPreset('ollama/qwen3.5:9b');
      }
      if (cfg.base_url) setBaseUrl(cfg.base_url);
    }).catch(() => {});
  }, []);

  const preset = PRESET_MODELS.find(p => p.value === selectedPreset);

  const handlePresetChange = (value: string) => {
    setSelectedPreset(value);
    if (value !== 'custom') setModelName(value);
    else setModelName('');
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const finalModel = selectedPreset === 'custom' ? modelName : selectedPreset;
      await apiSaveModelConfig({
        model_name: finalModel || null,
        api_key: apiKey || null,
        base_url: baseUrl || null,
      });
      toast.success('Model configuration saved');
      onComplete();
    } catch (e: any) {
      toast.error('Failed to save: ' + e.message);
    }
    setSaving(false);
  };

  const handleReset = async () => {
    setResetting(true);
    try {
      await apiResetModelConfig();
      setModelName(''); setApiKey(''); setBaseUrl('');
      setSelectedPreset('ollama/qwen3.5:9b');
      toast.success('Reset to system defaults');
    } catch (e: any) {
      toast.error(e.message);
    }
    setResetting(false);
  };

  const inputClass = 'w-full rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition-all';
  const labelClass = 'block text-sm font-medium text-foreground mb-1.5';

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-bold text-foreground">AI Model Configuration</h2>
        <p className="text-muted-foreground text-sm mt-1">
          Choose the LLM used for invoice extraction. Leave blank to use the system default.
        </p>
      </div>

      {config && (
        <div className="mb-4 p-3 rounded-lg bg-surface-2 border border-border text-sm text-muted-foreground flex items-center gap-2">
          <Info size={14} />
          Current effective model: <strong className="text-foreground">{config.effective_model}</strong>
        </div>
      )}

      <div className="space-y-4">
        <div>
          <label className={labelClass}>Model Preset</label>
          <select value={selectedPreset} onChange={e => handlePresetChange(e.target.value)} className={inputClass}>
            {PRESET_MODELS.map(p => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>

        {selectedPreset === 'custom' && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
            <label className={labelClass}>Model Name</label>
            <input value={modelName} onChange={e => setModelName(e.target.value)}
              placeholder="e.g. ollama/mistral:7b or groq/mixtral-8x7b" className={inputClass} />
            <p className="text-xs text-muted-foreground mt-1">Format: provider/model-name</p>
          </motion.div>
        )}

        {preset?.needsKey && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
            <label className={labelClass}>API Key</label>
            <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
              placeholder="Your API key" className={inputClass} />
            {config?.api_key && <p className="text-xs text-success mt-1 flex items-center gap-1"><CheckCircle size={11} /> API key saved</p>}
          </motion.div>
        )}

        {(preset?.needsUrl || selectedPreset === 'custom') && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
            <label className={labelClass}>Base URL (Ollama server)</label>
            <input value={baseUrl} onChange={e => setBaseUrl(e.target.value)}
              placeholder="http://your-ollama-server:11434" className={inputClass} />
            <p className="text-xs text-muted-foreground mt-1">Leave blank to use the system default Ollama URL</p>
          </motion.div>
        )}
      </div>

      <div className="flex items-center justify-between pt-6">
        <div className="flex gap-2">
          <button type="button" onClick={onBack} className="px-4 h-10 rounded-lg border border-border text-sm font-medium text-foreground hover:bg-muted transition-all">
            ← Back
          </button>
          <button type="button" onClick={handleReset} disabled={resetting}
            className="px-4 h-10 rounded-lg border border-border text-sm font-medium text-muted-foreground hover:bg-muted transition-all flex items-center gap-2 disabled:opacity-50">
            {resetting ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
            Use System Default
          </button>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onComplete} className="px-4 h-10 rounded-lg border border-border text-sm font-medium text-muted-foreground hover:bg-muted transition-all">
            Skip
          </button>
          <button type="button" onClick={handleSave} disabled={saving}
            className="px-6 h-10 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary-dark transition-all active:scale-[0.97] disabled:opacity-50 flex items-center gap-2">
            {saving && <Loader2 size={14} className="animate-spin" />}
            Save & Finish →
          </button>
        </div>
      </div>
    </div>
  );
}
