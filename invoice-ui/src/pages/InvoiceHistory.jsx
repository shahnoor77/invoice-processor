import { useEffect, useState } from 'react'
import { getInvoices, approveInvoice, rejectInvoice } from '../api'
import InvoiceCard from '../components/InvoiceCard'

const statusColor = (s) => {
  if (!s) return '#64748b'
  if (s === 'PENDING') return '#d97706'
  if (s.startsWith('APPROVED')) return '#16a34a'
  if (s.startsWith('REJECTED')) return '#dc2626'
  return '#64748b'
}

const badge = (status) => ({
  display: 'inline-block',
  padding: '2px 10px',
  borderRadius: 12,
  fontSize: 11,
  fontWeight: 700,
  background: statusColor(status) + '20',
  color: statusColor(status),
})

const s = {
  title: { fontSize: 22, fontWeight: 700, color: '#0f172a', marginBottom: 4 },
  sub: { fontSize: 14, color: '#64748b', marginBottom: 20 },
  table: { width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: 10, overflow: 'hidden', border: '1px solid #e2e8f0' },
  th: { padding: '12px 16px', textAlign: 'left', fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 1, background: '#f8fafc', borderBottom: '1px solid #e2e8f0' },
  td: { padding: '12px 16px', fontSize: 13, color: '#374151', borderBottom: '1px solid #f1f5f9' },
  btn: (color) => ({ padding: '6px 14px', background: color, color: '#fff', border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', marginRight: 6 }),
  modal: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 },
  modalBox: { background: '#fff', borderRadius: 12, padding: 32, width: '90%', maxWidth: 900, maxHeight: '90vh', overflowY: 'auto' },
  input: { width: '100%', padding: '10px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14, marginBottom: 12 },
  refresh: { padding: '8px 16px', background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 13, cursor: 'pointer', marginBottom: 16 },
}

export default function InvoiceHistory() {
  const [invoices, setInvoices] = useState([])
  const [selected, setSelected] = useState(null)
  const [rejectReason, setRejectReason] = useState('')
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState('')

  function load() {
    getInvoices().then(data => {
      setInvoices(Array.isArray(data) ? data : [])
    }).catch(err => console.error('Failed to load invoices:', err))
  }

  useEffect(() => { load() }, [])

  async function approve() {
    if (!selected) return
    setLoading(true)
    try {
      const inv = JSON.parse(selected['Full JSON'] || '{}')
      const rowNumber = selected._sheet_row || selected['_sheet_row']
      if (!rowNumber) throw new Error('Row number not found — refresh and try again')
      const result = await approveInvoice(rowNumber, inv)
      // Show routing results
      const routing = result.routing || {}
      const details = Object.entries(routing).map(([k, v]) => {
        if (Array.isArray(v)) return v.map(r => `${k}: ${r.success ? '✅' : '❌'} ${r.message}`).join(', ')
        return `${k}: ${v.success ? '✅' : '❌'} ${v.message}`
      }).join(' | ')
      setMsg(`✅ Invoice approved. ${details || 'No destinations configured.'}`)
      setSelected(null); load()
    } catch (e) { setMsg('❌ ' + e.message) }
    setLoading(false)
  }

  async function reject() {
    if (!selected) return
    setLoading(true)
    try {
      const inv = JSON.parse(selected['Full JSON'] || '{}')
      const rowNumber = selected._sheet_row || selected['_sheet_row']
      if (!rowNumber) throw new Error('Row number not found — refresh and try again')
      await rejectInvoice(rowNumber, inv, rejectReason)
      setMsg('Invoice rejected.')
      setSelected(null); load()
    } catch (e) { setMsg('❌ ' + e.message) }
    setLoading(false)
  }

  return (
    <div>
      <div style={s.title}>Invoice History</div>
      <div style={s.sub}>All processed invoices — approve or reject pending ones</div>
      {msg && <div style={{ marginBottom: 16, padding: '10px 14px', background: '#f0fdf4', borderRadius: 8, fontSize: 13, color: '#16a34a' }}>{msg}</div>}
      <button style={s.refresh} onClick={load}>🔄 Refresh</button>

      <table style={s.table}>
        <thead>
          <tr>
            {['Timestamp','Invoice #','Date','Due Date','Bill To','Total','Currency','Status',''].map(h => (
              <th key={h} style={s.th}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {invoices.length === 0 && (
            <tr><td colSpan={9} style={{ ...s.td, textAlign: 'center', color: '#94a3b8', padding: 32 }}>
              No invoices found. Process an invoice first, then refresh.
              {!localStorage.getItem('token') && ' (Not logged in)'}
            </td></tr>
          )}
          {invoices.map((inv, i) => (
            <tr key={i}>
              <td style={s.td}>{inv['Timestamp']}</td>
              <td style={{ ...s.td, fontWeight: 600 }}>{inv['Invoice Number'] || '—'}</td>
              <td style={s.td}>{inv['Invoice Date'] || '—'}</td>
              <td style={s.td}>{inv['Due Date'] || '—'}</td>
              <td style={s.td}>{inv['Receiver Name'] || '—'}</td>
              <td style={s.td}>{inv['Total Amount'] || '—'}</td>
              <td style={s.td}>{inv['Currency'] || '—'}</td>
              <td style={s.td}><span style={badge(inv['Approval Status'])}>{inv['Approval Status'] || '—'}</span></td>
              <td style={s.td}>
                <button style={s.btn('#1a56db')} onClick={() => { setSelected(inv); setRejectReason(''); setMsg('') }}>
                  View
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {selected && (
        <div style={s.modal} onClick={e => e.target === e.currentTarget && setSelected(null)}>
          <div style={s.modalBox}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <strong style={{ fontSize: 16 }}>Invoice #{selected['Invoice Number'] || '—'}</strong>
              <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: '#64748b' }}>✕</button>
            </div>

            {selected['Full JSON'] && (() => {
              try { return <InvoiceCard invoice={JSON.parse(selected['Full JSON'])} /> }
              catch { return null }
            })()}

            {selected['Approval Status'] === 'PENDING' && (
              <div style={{ marginTop: 20, paddingTop: 20, borderTop: '1px solid #e2e8f0' }}>
                <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end' }}>
                  <div style={{ flex: 1 }}>
                    <label style={{ fontSize: 13, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 6 }}>Rejection reason (optional)</label>
                    <input style={s.input} value={rejectReason} onChange={e => setRejectReason(e.target.value)} placeholder="Enter reason..." />
                  </div>
                  <button style={s.btn('#16a34a')} onClick={approve} disabled={loading}>✅ Approve</button>
                  <button style={s.btn('#dc2626')} onClick={reject} disabled={loading}>❌ Reject</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
