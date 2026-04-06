export default function InvoiceCard({ invoice: inv }) {
  if (!inv) return null
  const sender = inv.sender || {}
  const receiver = inv.receiver || {}
  const items = inv.line_items || []
  const cur = inv.currency || ''

  const fmt = v => (v == null || v === '' || v === 'null') ? '—' : String(v)
  const fmtMoney = v => {
    if (v == null || v === '' || v === 'null') return '—'
    try { return `${cur} ${parseFloat(String(v).replace(',','')).toFixed(2)}` }
    catch { return String(v) }
  }

  return (
    <div style={{ fontFamily: 'inherit', background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: 28 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24, paddingBottom: 20, borderBottom: '2px solid #1a56db' }}>
        <div>
          <div style={{ fontSize: 26, fontWeight: 800, color: '#1a56db', letterSpacing: 2 }}>INVOICE</div>
          <div style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>#{fmt(inv.invoice_number)}</div>
        </div>
        <div style={{ textAlign: 'right', fontSize: 13, color: '#64748b' }}>
          <div>Date: <strong style={{ color: '#0f172a' }}>{fmt(inv.invoice_date)}</strong></div>
          <div style={{ marginTop: 4 }}>Due: <strong style={{ color: '#1a56db' }}>{fmt(inv.due_date)}</strong></div>
          {inv.payment_terms && <div style={{ marginTop: 4 }}>Terms: {fmt(inv.payment_terms)}</div>}
        </div>
      </div>

      {/* From / Bill To */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
        {[['FROM', sender], ['BILL TO', receiver]].map(([label, party]) => (
          <div key={label} style={{ background: '#f0f7ff', border: '1px solid #bfdbfe', borderRadius: 8, padding: 16 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: '#1a56db', textTransform: 'uppercase', letterSpacing: 2, marginBottom: 10 }}>{label}</div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>{fmt(party.name)}</div>
            <div style={{ fontSize: 13, color: '#4b5563', marginTop: 4 }}>{fmt(party.address)}</div>
            <div style={{ fontSize: 13, color: '#4b5563' }}>{[party.city, party.country].filter(Boolean).join(', ') || '—'}</div>
            {party.phone && party.phone !== 'null' && <div style={{ fontSize: 13, color: '#4b5563', marginTop: 4 }}>📞 {party.phone}</div>}
            {party.email && party.email !== 'null' && <div style={{ fontSize: 13, color: '#4b5563' }}>✉️ {party.email}</div>}
          </div>
        ))}
      </div>

      {/* Line Items */}
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 20 }}>
        <thead>
          <tr style={{ background: '#1a56db', color: '#fff' }}>
            {['Description', 'Qty', 'Unit Price', 'Discount', 'Total'].map(h => (
              <th key={h} style={{ padding: '10px 12px', textAlign: h === 'Description' ? 'left' : 'right', fontSize: 12, fontWeight: 600 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.length === 0 && <tr><td colSpan={5} style={{ padding: 16, textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>No line items</td></tr>}
          {items.map((item, i) => (
            <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
              <td style={{ padding: '10px 12px', fontSize: 13 }}>{fmt(item.description)}</td>
              <td style={{ padding: '10px 12px', fontSize: 13, textAlign: 'right' }}>{fmt(item.quantity)}</td>
              <td style={{ padding: '10px 12px', fontSize: 13, textAlign: 'right' }}>{fmtMoney(item.unit_price)}</td>
              <td style={{ padding: '10px 12px', fontSize: 13, textAlign: 'right' }}>{fmtMoney(item.discount)}</td>
              <td style={{ padding: '10px 12px', fontSize: 13, textAlign: 'right', fontWeight: 600, color: '#1a56db' }}>{fmtMoney(item.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Totals */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <table style={{ width: 280, borderCollapse: 'collapse', background: '#f9fafb', border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden' }}>
          {[
            ['Subtotal', fmtMoney(inv.subtotal)],
            inv.tax_amount ? [`Tax (${fmt(inv.tax_rate)}%)`, fmtMoney(inv.tax_amount)] : null,
            inv.shipping ? ['Shipping', fmtMoney(inv.shipping)] : null,
          ].filter(Boolean).map(([k, v]) => (
            <tr key={k}><td style={{ padding: '7px 12px', fontSize: 13, color: '#64748b' }}>{k}</td><td style={{ padding: '7px 12px', fontSize: 13, textAlign: 'right' }}>{v}</td></tr>
          ))}
          <tr style={{ borderTop: '2px solid #1a56db', background: '#eff6ff' }}>
            <td style={{ padding: '10px 12px', fontWeight: 700, fontSize: 15, color: '#1a56db' }}>TOTAL</td>
            <td style={{ padding: '10px 12px', fontWeight: 700, fontSize: 15, textAlign: 'right', color: '#1a56db' }}>{fmtMoney(inv.total_amount)}</td>
          </tr>
          {inv.amount_due && <tr style={{ background: '#fefce8' }}>
            <td style={{ padding: '8px 12px', fontWeight: 600, fontSize: 13, color: '#854d0e' }}>Amount Due</td>
            <td style={{ padding: '8px 12px', fontWeight: 600, fontSize: 13, textAlign: 'right', color: '#854d0e' }}>{fmtMoney(inv.amount_due)}</td>
          </tr>}
        </table>
      </div>

      {inv.notes && inv.notes !== 'null' && <div style={{ padding: '12px 16px', background: '#eff6ff', borderLeft: '3px solid #1a56db', borderRadius: 4, fontSize: 13, color: '#1e40af', marginBottom: 8 }}><strong>Notes:</strong> {inv.notes}</div>}
      {inv.bank_details && inv.bank_details !== 'null' && <div style={{ padding: '12px 16px', background: '#f0fdf4', borderLeft: '3px solid #16a34a', borderRadius: 4, fontSize: 13, color: '#166534' }}><strong>Bank:</strong> {inv.bank_details}</div>}

      {inv.math_warnings?.length > 0 && (
        <div style={{ marginTop: 12, padding: '10px 14px', background: '#fef3c7', borderRadius: 8, fontSize: 13, color: '#92400e' }}>
          ⚠️ Math discrepancies: {inv.math_warnings.join(' | ')}
        </div>
      )}
    </div>
  )
}
