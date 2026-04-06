const BASE = '/api'

function getToken() {
  return localStorage.getItem('token')
}

function headers(extra = {}) {
  return {
    'Content-Type': 'application/json',
    ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    ...extra,
  }
}

async function req(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: headers(),
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

// Auth
export const login = (email, password) =>
  fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: email, password }),
  }).then(async r => {
    if (!r.ok) throw new Error((await r.json()).detail)
    return r.json()
  })

export const register = (email, password, name) =>
  req('POST', '/auth/register', { email, password, name })

export const getMe = () => req('GET', '/auth/me')

// Settings
export const getSettings = () => req('GET', '/settings')
export const saveSettings = (settings) => req('PUT', '/settings', settings)

// Invoices
export const getInvoices = () => req('GET', '/invoices')
export const approveInvoice = (rowNumber, invoiceData) =>
  req('PATCH', `/invoices/${rowNumber}/approve`, { row_number: rowNumber, invoice_data: invoiceData })
export const rejectInvoice = (rowNumber, invoiceData, reason) =>
  req('PATCH', `/invoices/${rowNumber}/reject`, { row_number: rowNumber, invoice_data: invoiceData, reject_reason: reason })

export const processInvoice = async (file, erpSystem, notificationChannel) => {
  const form = new FormData()
  form.append('file', file)
  form.append('erp_system', erpSystem)
  form.append('notification_channel', notificationChannel)
  const res = await fetch(`${BASE}/invoices/process`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}` },
    body: form,
  })
  if (!res.ok) throw new Error((await res.json()).detail)
  return res.json()
}

export const pollJob = (jobId) => req('GET', `/invoices/status/${jobId}`)

// Health
export const getHealth = () => req('GET', '/health')
