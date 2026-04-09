const BASE = '/api'

function getToken(): string | null {
  return localStorage.getItem('token')
}

function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

// Auth
export const apiLogin = (email: string, password: string) =>
  fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: email, password }),
  }).then(async r => {
    if (!r.ok) throw new Error((await r.json()).detail)
    return r.json() as Promise<{ access_token: string; token_type: string; name: string }>
  })

export const apiRegister = (email: string, password: string, name: string) =>
  req('POST', '/auth/register', { email, password, name })

// Invoices
export const apiGetInvoices = () => req<RealInvoice[]>('GET', '/invoices')
export const apiGetInvoice = (id: string) => req<RealInvoice>('GET', `/invoices/${id}`)
export const apiApproveInvoice = (id: string) => req('PATCH', `/invoices/${id}/approve`)
export const apiRejectInvoice = (id: string, reason?: string) =>
  req('PATCH', `/invoices/${id}/reject`, { reject_reason: reason })

export const apiUploadInvoice = async (file: File): Promise<{ job_id: string; status: string }> => {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/invoices/upload`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  })
  if (!res.ok) throw new Error((await res.json()).detail)
  return res.json()
}

export const apiPollJob = (jobId: string) => req<JobStatus>('GET', `/invoices/jobs/${jobId}`)

// Settings
export const apiGetEmailConfig = () => req('GET', '/settings/email')
export const apiSaveEmailConfig = (data: unknown) => req('PUT', '/settings/email', data)
export const apiTestEmailConnection = () => req('POST', '/settings/email/test')
export const apiPollNow = () => req('POST', '/settings/email/poll-now')
export const apiGetWebhooks = () => req('GET', '/settings/webhooks')
export const apiCreateWebhook = (data: unknown) => req('POST', '/settings/webhooks', data)
export const apiUpdateWebhook = (id: string, data: unknown) => req('PUT', `/settings/webhooks/${id}`, data)
export const apiDeleteWebhook = (id: string) => req('DELETE', `/settings/webhooks/${id}`)
export const apiTestWebhook = (id: string) => req('POST', `/settings/webhooks/${id}/test`)

// Model config
export const apiGetModelConfig = () => req('GET', '/settings/model')
export const apiSaveModelConfig = (data: unknown) => req('PUT', '/settings/model', data)
export const apiResetModelConfig = () => req('DELETE', '/settings/model')

// Types matching our DB schema
export interface RealInvoice {
  id: string
  invoice_number: string | null
  invoice_date: string | null
  due_date: string | null
  delivery_date: string | null
  payment_terms: string | null
  payment_method: string | null
  purchase_order: string | null
  reference: string | null
  // Sender
  sender_name: string | null
  sender_address: string | null
  sender_city: string | null
  sender_state: string | null
  sender_zip: string | null
  sender_country: string | null
  sender_email: string | null
  sender_phone: string | null
  sender_website: string | null
  sender_tax_id: string | null
  sender_vat_number: string | null
  sender_registration: string | null
  sender_bank_name: string | null
  sender_bank_account_holder: string | null
  sender_bank_account_number: string | null
  sender_bank_iban: string | null
  sender_bank_swift: string | null
  sender_bank_routing: string | null
  sender_bank_sort_code: string | null
  sender_bank_branch: string | null
  sender_bank_address: string | null
  // Receiver
  receiver_name: string | null
  receiver_address: string | null
  receiver_city: string | null
  receiver_state: string | null
  receiver_zip: string | null
  receiver_country: string | null
  receiver_email: string | null
  receiver_phone: string | null
  receiver_tax_id: string | null
  receiver_vat_number: string | null
  receiver_bank_name: string | null
  receiver_bank_account_holder: string | null
  receiver_bank_account_number: string | null
  receiver_bank_iban: string | null
  receiver_bank_swift: string | null
  receiver_bank_routing: string | null
  receiver_bank_sort_code: string | null
  receiver_bank_branch: string | null
  // Financials
  currency: string | null
  exchange_rate: number | null
  subtotal: number | null
  discount_total: number | null
  discount_percent: number | null
  tax_rate: number | null
  tax_amount: number | null
  tax_type: string | null
  shipping: number | null
  handling: number | null
  other_charges: number | null
  total_amount: number | null
  amount_paid: number | null
  amount_due: number | null
  deposit: number | null
  notes: string | null
  terms_and_conditions: string | null
  ocr_confidence: string | null
  approval_status: string
  approved_by: string | null
  approved_at: string | null
  rejected_reason: string | null
  file_name: string | null
  source: string
  created_at: string
  line_items: LineItem[]
}

export interface LineItem {
  id: string
  description: string | null
  quantity: number | null
  unit_price: number | null
  total: number | null
}

export interface JobStatus {
  id: string
  status: 'queued' | 'processing' | 'done' | 'failed'
  error_message: string | null
  invoice?: RealInvoice
}
