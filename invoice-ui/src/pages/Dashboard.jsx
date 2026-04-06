import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getInvoices, getHealth } from '../api'

const s = {
  title: { fontSize: 22, fontWeight: 700, color: '#0f172a', marginBottom: 4 },
  sub: { fontSize: 14, color: '#64748b', marginBottom: 28 },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 32 },
  card: { background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: '20px 24px' },
  cardLabel: { fontSize: 12, color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1 },
  cardValue: { fontSize: 28, fontWeight: 700, color: '#0f172a', marginTop: 6 },
  cardSub: { fontSize: 12, color: '#94a3b8', marginTop: 4 },
  statusDot: (ok) => ({ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: ok ? '#22c55e' : '#ef4444', marginRight: 6 }),
  btn: { padding: '10px 20px', background: '#1a56db', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer' },
  healthCard: { background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: 20, marginBottom: 24 },
}

export default function Dashboard() {
  const [invoices, setInvoices] = useState([])
  const [health, setHealth] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    getInvoices().then(setInvoices).catch(() => {})
    getHealth().then(setHealth).catch(() => {})
  }, [])

  const total = invoices.length
  const pending = invoices.filter(i => i['Approval Status'] === 'PENDING').length
  const approved = invoices.filter(i => (i['Approval Status'] || '').startsWith('APPROVED')).length
  const rejected = invoices.filter(i => (i['Approval Status'] || '').startsWith('REJECTED')).length

  return (
    <div>
      <div style={s.title}>Dashboard</div>
      <div style={s.sub}>Overview of your invoice processing activity</div>

      {health && (
        <div style={s.healthCard}>
          <span style={s.statusDot(health.model_reachable)} />
          <strong>AI Model:</strong> {health.active_model} —
          <span style={{ color: health.model_reachable ? '#16a34a' : '#dc2626', marginLeft: 4 }}>
            {health.model_reachable ? 'Connected' : 'Unreachable'}
          </span>
          <span style={{ marginLeft: 20 }}>
            <span style={s.statusDot(health.sheets_configured)} />
            <strong>Google Sheets:</strong> {health.sheets_configured ? 'Configured' : 'Not configured'}
          </span>
        </div>
      )}

      <div style={s.grid}>
        {[
          { label: 'Total Processed', value: total, sub: 'All time' },
          { label: 'Pending Review', value: pending, sub: 'Awaiting approval', color: '#d97706' },
          { label: 'Approved', value: approved, sub: 'Sent to ERP', color: '#16a34a' },
          { label: 'Rejected', value: rejected, sub: 'Logged & closed', color: '#dc2626' },
        ].map(c => (
          <div key={c.label} style={s.card}>
            <div style={s.cardLabel}>{c.label}</div>
            <div style={{ ...s.cardValue, color: c.color || '#0f172a' }}>{c.value}</div>
            <div style={s.cardSub}>{c.sub}</div>
          </div>
        ))}
      </div>

      <button style={s.btn} onClick={() => navigate('/process')}>
        + Process New Invoice
      </button>
    </div>
  )
}
