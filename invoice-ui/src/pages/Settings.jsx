import { useEffect, useState } from 'react'
import { getSettings, saveSettings } from '../api'

const s = {
  title: { fontSize: 22, fontWeight: 700, color: '#0f172a', marginBottom: 4 },
  sub: { fontSize: 14, color: '#64748b', marginBottom: 28 },
  card: { background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: 28, marginBottom: 20 },
  sectionTitle: { fontSize: 15, fontWeight: 700, color: '#0f172a', marginBottom: 4 },
  sectionSub: { fontSize: 13, color: '#64748b', marginBottom: 16 },
  label: { display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 },
  input: { width: '100%', padding: '10px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14, outline: 'none', marginBottom: 8 },
  row: { display: 'flex', gap: 8, marginBottom: 8 },
  addBtn: { padding: '8px 14px', background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 13, cursor: 'pointer' },
  removeBtn: { padding: '8px 12px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, fontSize: 13, cursor: 'pointer', color: '#dc2626' },
  saveBtn: { padding: '11px 28px', background: '#1a56db', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer' },
  success: { background: '#f0fdf4', color: '#16a34a', padding: '10px 14px', borderRadius: 8, fontSize: 13, marginBottom: 16 },
}

function ListInput({ label, hint, values, onChange }) {
  function add() { onChange([...values, '']) }
  function update(i, v) { const a = [...values]; a[i] = v; onChange(a) }
  function remove(i) { onChange(values.filter((_, idx) => idx !== i)) }

  return (
    <div style={{ marginBottom: 20 }}>
      <label style={s.label}>{label}</label>
      <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>{hint}</div>
      {values.map((v, i) => (
        <div key={i} style={s.row}>
          <input style={{ ...s.input, marginBottom: 0, flex: 1 }} value={v} onChange={e => update(i, e.target.value)} placeholder="https://..." />
          <button type="button" style={s.removeBtn} onClick={() => remove(i)}>✕</button>
        </div>
      ))}
      <button type="button" style={s.addBtn} onClick={add}>+ Add</button>
    </div>
  )
}

export default function Settings() {
  const [settings, setSettings] = useState({ erp_webhooks: [], notification_emails: [], slack_webhooks: [], google_sheet_id: '' })
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    getSettings().then(data => setSettings({ erp_webhooks: [], notification_emails: [], slack_webhooks: [], google_sheet_id: '', ...data })).catch(() => {})
  }, [])

  async function save() {
    setLoading(true)
    try {
      await saveSettings(settings)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) { alert(e.message) }
    setLoading(false)
  }

  return (
    <div>
      <div style={s.title}>Settings</div>
      <div style={s.sub}>Configure your destinations — changes apply to all future approvals</div>
      {saved && <div style={s.success}>✅ Settings saved successfully</div>}

      <div style={s.card}>
        <div style={s.sectionTitle}>ERP Webhooks</div>
        <div style={s.sectionSub}>Approved invoices will be POSTed as JSON to these URLs</div>
        <ListInput label="Webhook URLs" hint="Add one or more ERP webhook endpoints"
          values={settings.erp_webhooks} onChange={v => setSettings(p => ({ ...p, erp_webhooks: v }))} />
      </div>

      <div style={s.card}>
        <div style={s.sectionTitle}>Email Notifications</div>
        <div style={s.sectionSub}>Send invoice summary emails on approval</div>
        <ListInput label="Email Addresses" hint="Add one or more recipient emails"
          values={settings.notification_emails} onChange={v => setSettings(p => ({ ...p, notification_emails: v }))} />
      </div>

      <div style={s.card}>
        <div style={s.sectionTitle}>Slack Notifications</div>
        <div style={s.sectionSub}>Post to Slack channels via incoming webhooks</div>
        <ListInput label="Slack Webhook URLs" hint="Get from Slack App → Incoming Webhooks"
          values={settings.slack_webhooks} onChange={v => setSettings(p => ({ ...p, slack_webhooks: v }))} />
      </div>

      <div style={s.card}>
        <div style={s.sectionTitle}>Google Sheets</div>
        <div style={s.sectionSub}>Override the default sheet ID for your account</div>
        <label style={s.label}>Sheet ID</label>
        <input style={s.input} value={settings.google_sheet_id || ''} onChange={e => setSettings(p => ({ ...p, google_sheet_id: e.target.value }))} placeholder="From your Google Sheet URL" />
      </div>

      <button style={s.saveBtn} onClick={save} disabled={loading}>
        {loading ? 'Saving...' : 'Save Settings'}
      </button>
    </div>
  )
}
