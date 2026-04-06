import { useState, useRef, useEffect } from 'react'
import { processInvoice, pollJob, approveInvoice, rejectInvoice, getInvoices } from '../api'
import { useApp } from '../context/AppContext'
import InvoiceCard from '../components/InvoiceCard'

const s = {
  title: { fontSize: 22, fontWeight: 700, color: '#0f172a', marginBottom: 4 },
  sub: { fontSize: 14, color: '#64748b', marginBottom: 28 },
  card: { background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: 28, marginBottom: 20 },
  label: { display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 },
  input: { width: '100%', padding: '10px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14, outline: 'none', marginBottom: 16 },
  row: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 },
  btn: { padding: '11px 24px', background: '#1a56db', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer' },
  btnSec: { padding: '11px 24px', background: '#f1f5f9', color: '#374151', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer' },
  btnDisabled: { opacity: 0.5, cursor: 'not-allowed' },
  dropzone: { border: '2px dashed #bfdbfe', borderRadius: 10, padding: '40px 20px', textAlign: 'center', cursor: 'pointer', background: '#f0f7ff', marginBottom: 20 },
  spinner: { display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '60px 0' },
  error: { background: '#fef2f2', color: '#dc2626', padding: '12px 16px', borderRadius: 8, fontSize: 13, marginBottom: 16 },
  success: { background: '#f0fdf4', color: '#16a34a', padding: '12px 16px', borderRadius: 8, fontSize: 13, marginBottom: 16 },
  tabs: { display: 'flex', gap: 0, marginBottom: 20, border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden' },
  tab: (active) => ({ flex: 1, padding: '10px', textAlign: 'center', fontSize: 13, fontWeight: 600, cursor: 'pointer', background: active ? '#1a56db' : '#fff', color: active ? '#fff' : '#64748b', border: 'none' }),
  emailItem: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', border: '1px solid #e2e8f0', borderRadius: 8, marginBottom: 8, background: '#fff' },
}

export default function ProcessInvoice() {
  const { processingState, setProcessingState } = useApp()
  const { phase, result, error } = processingState

  const [tab, setTab] = useState('upload')
  const [file, setFile] = useState(null)
  const [erp, setErp] = useState('')
  const [channel, setChannel] = useState('')
  const [dots, setDots] = useState('')
  const [emailAddr, setEmailAddr] = useState('')
  const [emailPass, setEmailPass] = useState('')
  const [emailFrom, setEmailFrom] = useState('')
  const [emailSubject, setEmailSubject] = useState('')
  const [fetchedEmails, setFetchedEmails] = useState([])
  const [fetchingEmail, setFetchingEmail] = useState(false)
  const [emailError, setEmailError] = useState('')
  const fileRef = useRef()
  const pollRef = useRef()

  const setPhase = (p) => setProcessingState(s => ({ ...s, phase: p }))
  const setResult = (r) => setProcessingState(s => ({ ...s, result: r }))
  const setError = (e) => setProcessingState(s => ({ ...s, error: e }))

  useEffect(() => {
    if (phase === 'processing') {
      const t = setInterval(() => setDots(d => d.length >= 3 ? '' : d + '.'), 500)
      return () => clearInterval(t)
    }
  }, [phase])

  function onDrop(e) {
    e.preventDefault()
    const f = e.dataTransfer?.files[0] || e.target.files[0]
    if (f) setFile(f)
  }

  async function submit(e) {
    e.preventDefault()
    if (!file) return
    setError(''); setPhase('processing')
    try {
      const { job_id } = await processInvoice(file, erp, channel)
      let attempts = 0
      pollRef.current = setInterval(async () => {
        attempts++
        try {
          const job = await pollJob(job_id)
          if (job.status === 'done') {
            clearInterval(pollRef.current)
            if (job.result) {
              setResult(job.result)
              setPhase('done')
            } else {
              setError('Processing completed but no data was extracted. Check the model connection.')
              setPhase('error')
            }
          } else if (job.status === 'failed') {
            clearInterval(pollRef.current)
            setError(job.error || 'Processing failed')
            setPhase('error')
          } else if (attempts > 120) { // 6 min timeout
            clearInterval(pollRef.current)
            setError('Processing timed out. The model may be slow or unreachable.')
            setPhase('error')
          }
        } catch (pollErr) {
          clearInterval(pollRef.current)
          setError(pollErr.message)
          setPhase('error')
        }
      }, 3000)
    } catch (err) {
      setError(err.message); setPhase('error')
    }
  }

  function reset() {
    setProcessingState({ phase: 'idle', result: null, error: '', jobId: null, fileName: '' })
    setFile(null); setFetchedEmails([]); setEmailError('')
  }

  async function handleApprove(inv) {
    try {
      // Find the row number from the sheet
      const records = await getInvoices()
      const idx = records.findIndex(r => r['Invoice Number'] === inv.invoice_number)
      const rowNumber = idx >= 0 ? idx + 2 : 2
      await approveInvoice(rowNumber, inv)
      setPhase('approved')
    } catch (e) {
      setError('Approval failed: ' + e.message)
    }
  }

  async function handleReject(inv) {
    const reason = window.prompt('Rejection reason (optional):') || ''
    try {
      const records = await getInvoices()
      const idx = records.findIndex(r => r['Invoice Number'] === inv.invoice_number)
      const rowNumber = idx >= 0 ? idx + 2 : 2
      await rejectInvoice(rowNumber, inv, reason)
      setPhase('rejected')
    } catch (e) {
      setError('Rejection failed: ' + e.message)
    }
  }

  async function fetchEmails(e) {
    e.preventDefault()
    setFetchingEmail(true); setEmailError(''); setFetchedEmails([])
    try {
      const res = await fetch('/api/email/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` },
        body: JSON.stringify({ email: emailAddr, password: emailPass, max_emails: 10, unread_only: false, from_filter: emailFrom, subject_filter: emailSubject }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to fetch emails')
      setFetchedEmails(data.emails || [])
      if (data.emails?.length === 0) setEmailError('No emails with invoice attachments found.')
    } catch (err) { setEmailError(err.message) }
    setFetchingEmail(false)
  }

  async function processAttachment(path, name) {
    setError(''); setPhase('processing')
    const form = new FormData()
    form.append('file_path', path)
    form.append('file_name', name)
    form.append('erp_system', erp)
    form.append('notification_channel', channel)
    try {
      const res = await fetch('/api/email/process-attachment', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
        body: form,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail)
      const job_id = data.job_id
      let attempts = 0
      pollRef.current = setInterval(async () => {
        attempts++
        const job = await pollJob(job_id)
        if (job.status === 'done') {
          clearInterval(pollRef.current)
          setResult(job.result); setPhase('done')
        } else if (job.status === 'failed' || attempts > 120) {
          clearInterval(pollRef.current)
          setError(job.error || 'Processing failed'); setPhase('error')
        }
      }, 3000)
    } catch (err) { setError(err.message); setPhase('error') }
  }

  return (
    <div>
      <div style={s.title}>Process Invoice</div>
      <div style={s.sub}>Upload a file or fetch from email</div>

      {phase === 'idle' && (
        <>
          <div style={s.tabs}>
            <button style={s.tab(tab === 'upload')} onClick={() => setTab('upload')}>📁 Upload File</button>
            <button style={s.tab(tab === 'email')} onClick={() => setTab('email')}>📧 Fetch from Email</button>
          </div>

          {tab === 'upload' && (
            <form onSubmit={submit}>
              <div style={s.dropzone} onClick={() => fileRef.current.click()} onDrop={onDrop} onDragOver={e => e.preventDefault()}>
                <input ref={fileRef} type="file" accept=".pdf,.png,.jpg,.jpeg" style={{ display: 'none' }} onChange={onDrop} />
                {file ? (
                  <div><div style={{ fontSize: 32 }}>📄</div><div style={{ fontWeight: 600, marginTop: 8 }}>{file.name}</div><div style={{ fontSize: 12, color: '#64748b' }}>{(file.size / 1024).toFixed(1)} KB</div></div>
                ) : (
                  <div><div style={{ fontSize: 32 }}>📂</div><div style={{ fontWeight: 600, marginTop: 8 }}>Drop invoice here or click to browse</div><div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>PDF, PNG, JPG supported</div></div>
                )}
              </div>
              <div style={s.card}>
                <div style={s.row}>
                  <div><label style={s.label}>ERP System</label><input style={s.input} value={erp} onChange={e => setErp(e.target.value)} placeholder="SAP, QuickBooks..." /></div>
                  <div><label style={s.label}>Notification Channel</label><input style={s.input} value={channel} onChange={e => setChannel(e.target.value)} placeholder="email, Slack #finance..." /></div>
                </div>
                <button style={{ ...s.btn, ...(!file ? s.btnDisabled : {}) }} type="submit" disabled={!file}>🚀 Process Invoice</button>
              </div>
            </form>
          )}

          {tab === 'email' && (
            <div>
              <div style={s.card}>
                <form onSubmit={fetchEmails}>
                  <div style={s.row}>
                    <div><label style={s.label}>Email Address</label><input style={s.input} type="email" value={emailAddr} onChange={e => setEmailAddr(e.target.value)} placeholder="you@company.com" required /></div>
                    <div><label style={s.label}>Password / App Password</label><input style={s.input} type="password" value={emailPass} onChange={e => setEmailPass(e.target.value)} placeholder="Gmail: use App Password" required /></div>
                  </div>
                  <div style={s.row}>
                    <div><label style={s.label}>From (optional filter)</label><input style={s.input} value={emailFrom} onChange={e => setEmailFrom(e.target.value)} placeholder="vendor@acme.com" /></div>
                    <div><label style={s.label}>Subject contains (optional)</label><input style={s.input} value={emailSubject} onChange={e => setEmailSubject(e.target.value)} placeholder="invoice" /></div>
                  </div>
                  <button style={s.btn} type="submit" disabled={fetchingEmail}>{fetchingEmail ? 'Fetching...' : '📧 Fetch Emails'}</button>
                </form>
              </div>

              {emailError && <div style={s.error}>{emailError}</div>}

              {fetchedEmails.length > 0 && (
                <div style={s.card}>
                  <div style={{ fontWeight: 600, marginBottom: 12 }}>{fetchedEmails.length} email(s) with attachments found</div>
                  <div style={s.row}>
                    <div><label style={s.label}>ERP System</label><input style={s.input} value={erp} onChange={e => setErp(e.target.value)} placeholder="SAP, QuickBooks..." /></div>
                    <div><label style={s.label}>Notification Channel</label><input style={s.input} value={channel} onChange={e => setChannel(e.target.value)} placeholder="email, Slack..." /></div>
                  </div>
                  {fetchedEmails.map((em, i) => (
                    <div key={i} style={{ marginBottom: 12 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{em.subject}</div>
                      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 8 }}>{em.sender} · {em.date}</div>
                      {em.attachments.map((att, j) => (
                        <div key={j} style={s.emailItem}>
                          <span style={{ fontSize: 13 }}>📎 {att.name}</span>
                          <button style={{ ...s.btn, padding: '6px 14px', fontSize: 12 }} onClick={() => processAttachment(att.path, att.name)}>Process</button>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {phase === 'processing' && (
        <div style={s.spinner}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>⚙️</div>
          <div style={{ fontSize: 18, fontWeight: 600, color: '#1a56db' }}>Processing Invoice{dots}</div>
          <div style={{ fontSize: 13, color: '#64748b', marginTop: 8 }}>AI agents are extracting and validating data</div>
        </div>
      )}

      {phase === 'error' && (
        <div>
          <div style={s.error}>❌ {error}</div>
          <button style={s.btn} onClick={reset}>Try Again</button>
        </div>
      )}

      {phase === 'done' && result && (
        <div>
          <div style={s.success}>✅ Invoice processed and saved as PENDING. Review below and approve or reject.</div>
          <InvoiceCard invoice={result} />
          <div style={{ display: 'flex', gap: 12, marginTop: 20, padding: 20, background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Ready to approve this invoice?</div>
              <div style={{ fontSize: 13, color: '#64748b' }}>Approving will send it to your configured destinations (ERP, email, Slack).</div>
            </div>
            <button style={{ ...s.btn, background: '#16a34a', padding: '10px 24px' }} onClick={() => handleApprove(result)}>✅ Approve</button>
            <button style={{ ...s.btn, background: '#dc2626', padding: '10px 24px' }} onClick={() => handleReject(result)}>❌ Reject</button>
          </div>
          <button style={{ ...s.btnSec, marginTop: 12 }} onClick={reset}>Process Another Invoice</button>
        </div>
      )}

      {phase === 'approved' && (
        <div>
          <div style={s.success}>✅ Invoice approved and sent to destinations.</div>
          <button style={s.btn} onClick={reset}>Process Another Invoice</button>
        </div>
      )}

      {phase === 'rejected' && (
        <div>
          <div style={{ ...s.error, background: '#fef3c7', color: '#92400e' }}>Invoice rejected and logged.</div>
          <button style={s.btn} onClick={reset}>Process Another Invoice</button>
        </div>
      )}
    </div>
  )
}
