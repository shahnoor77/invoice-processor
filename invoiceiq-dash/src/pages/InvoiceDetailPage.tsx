import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, CheckCircle, XCircle, Loader2, MapPin, Phone, Hash, Clock, Receipt, Calendar, CreditCard, Mail, Pencil, Save, Plus, Trash2 } from 'lucide-react';
import { apiGetInvoice, apiApproveInvoice, apiRejectInvoice, apiPatchInvoice, RealInvoice } from '@/lib/api';
import { StatusBadge } from '@/components/invoice/StatusBadge';
import { toast } from 'sonner';

function mapStatus(s: string): 'Pending' | 'Approved' | 'Rejected' {
  if (s === 'APPROVED') return 'Approved';
  if (s === 'REJECTED') return 'Rejected';
  return 'Pending';
}

type ValidationIssue = { field: string; original: number; corrected: number; note: string };

type EditableLineItem = {
  description: string;
  quantity: string;
  unit_price: string;
  total: string;
};

type EditableInvoice = {
  invoice_number: string;
  invoice_date: string;
  due_date: string;
  payment_terms: string;
  purchase_order: string;
  currency: string;
  sender_name: string;
  sender_email: string;
  sender_phone: string;
  sender_tax_id: string;
  sender_address: string;
  sender_city: string;
  sender_country: string;
  sender_bank_name: string;
  sender_bank_account_number: string;
  sender_bank_iban: string;
  sender_bank_swift: string;
  receiver_bank_name: string;
  receiver_bank_account_number: string;
  receiver_bank_iban: string;
  receiver_bank_swift: string;
  subtotal: string;
  tax_rate: string;
  tax_amount: string;
  total_amount: string;
  amount_paid: string;
  amount_due: string;
  notes: string;
  line_items: EditableLineItem[];
};

const asInput = (v: string | number | null | undefined) => (v == null ? '' : String(v));
const asNullableString = (v: string) => {
  const t = v.trim();
  return t ? t : null;
};
const asNullableNumber = (v: string) => {
  const t = v.trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
};
const getErrorMessage = (e: unknown) => (e instanceof Error ? e.message : 'Request failed');

function toEditableInvoice(inv: RealInvoice): EditableInvoice {
  return {
    invoice_number: asInput(inv.invoice_number),
    invoice_date: asInput(inv.invoice_date),
    due_date: asInput(inv.due_date),
    payment_terms: asInput(inv.payment_terms),
    purchase_order: asInput(inv.purchase_order),
    currency: asInput(inv.currency),
    sender_name: asInput(inv.sender_name),
    sender_email: asInput(inv.sender_email),
    sender_phone: asInput(inv.sender_phone),
    sender_tax_id: asInput(inv.sender_tax_id),
    sender_address: asInput(inv.sender_address),
    sender_city: asInput(inv.sender_city),
    sender_country: asInput(inv.sender_country),
    sender_bank_name: asInput(inv.sender_bank_name),
    sender_bank_account_number: asInput(inv.sender_bank_account_number),
    sender_bank_iban: asInput(inv.sender_bank_iban),
    sender_bank_swift: asInput(inv.sender_bank_swift),
    receiver_bank_name: asInput(inv.receiver_bank_name),
    receiver_bank_account_number: asInput(inv.receiver_bank_account_number),
    receiver_bank_iban: asInput(inv.receiver_bank_iban),
    receiver_bank_swift: asInput(inv.receiver_bank_swift),
    subtotal: asInput(inv.subtotal),
    tax_rate: asInput(inv.tax_rate),
    tax_amount: asInput(inv.tax_amount),
    total_amount: asInput(inv.total_amount),
    amount_paid: asInput(inv.amount_paid),
    amount_due: asInput(inv.amount_due),
    notes: asInput(inv.notes),
    line_items: (inv.line_items || []).map((li) => ({
      description: asInput(li.description),
      quantity: asInput(li.quantity),
      unit_price: asInput(li.unit_price),
      total: asInput(li.total),
    })),
  };
}

function toPatchPayload(draft: EditableInvoice): Record<string, unknown> {
  return {
    invoice_number: asNullableString(draft.invoice_number),
    invoice_date: asNullableString(draft.invoice_date),
    due_date: asNullableString(draft.due_date),
    payment_terms: asNullableString(draft.payment_terms),
    purchase_order: asNullableString(draft.purchase_order),
    currency: asNullableString(draft.currency),
    sender_name: asNullableString(draft.sender_name),
    sender_email: asNullableString(draft.sender_email),
    sender_phone: asNullableString(draft.sender_phone),
    sender_tax_id: asNullableString(draft.sender_tax_id),
    sender_address: asNullableString(draft.sender_address),
    sender_city: asNullableString(draft.sender_city),
    sender_country: asNullableString(draft.sender_country),
    sender_bank_name: asNullableString(draft.sender_bank_name),
    sender_bank_account_number: asNullableString(draft.sender_bank_account_number),
    sender_bank_iban: asNullableString(draft.sender_bank_iban),
    sender_bank_swift: asNullableString(draft.sender_bank_swift),
    receiver_bank_name: asNullableString(draft.receiver_bank_name),
    receiver_bank_account_number: asNullableString(draft.receiver_bank_account_number),
    receiver_bank_iban: asNullableString(draft.receiver_bank_iban),
    receiver_bank_swift: asNullableString(draft.receiver_bank_swift),
    subtotal: asNullableNumber(draft.subtotal),
    tax_rate: asNullableNumber(draft.tax_rate),
    tax_amount: asNullableNumber(draft.tax_amount),
    total_amount: asNullableNumber(draft.total_amount),
    amount_paid: asNullableNumber(draft.amount_paid),
    amount_due: asNullableNumber(draft.amount_due),
    notes: asNullableString(draft.notes),
    line_items: draft.line_items
      .filter((li) => li.description.trim() || li.quantity.trim() || li.unit_price.trim() || li.total.trim())
      .map((li) => ({
        description: asNullableString(li.description),
        quantity: asNullableNumber(li.quantity),
        unit_price: asNullableNumber(li.unit_price),
        total: asNullableNumber(li.total),
      })),
  };
}

/** Renders a value cell. If the field was auto-corrected, shows the wrong value struck-through in amber, then the correct value. */
function ValCell({ field, value, currency = '', issueMap }: {
  field: string;
  value: number | null | undefined;
  currency?: string;
  issueMap: Record<string, ValidationIssue>;
}) {
  const issue = issueMap[field];
  const fmt = (n: number) => `${currency} ${n.toFixed(2)}`.trim();
  if (value == null) return <span className="text-muted-foreground">—</span>;
  if (!issue) return <span>{fmt(value)}</span>;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="line-through text-amber-500/70 bg-amber-500/10 px-1 rounded text-[10px]" title={issue.note}>
        {fmt(issue.original)}
      </span>
      <span>{fmt(value)}</span>
    </span>
  );
}

export default function InvoiceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [invoice, setInvoice] = useState<RealInvoice | null>(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<'approve' | 'reject' | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [savingEdits, setSavingEdits] = useState(false);
  const [draft, setDraft] = useState<EditableInvoice | null>(null);

  useEffect(() => {
    if (!id) return;
    apiGetInvoice(id).then(setInvoice).catch(() => setInvoice(null)).finally(() => setLoading(false));
  }, [id]);

  const handleApprove = async () => {
    if (!invoice) return;
    setActionLoading(true);
    try {
      await apiApproveInvoice(invoice.id);
      setInvoice({ ...invoice, approval_status: 'APPROVED' });
      toast.success(`Invoice ${invoice.invoice_number || invoice.id} approved`);
    } catch (e: unknown) {
      toast.error(getErrorMessage(e));
    } finally {
      setActionLoading(false);
      setAction(null);
    }
  };

  const handleReject = async () => {
    if (!invoice) return;
    setActionLoading(true);
    try {
      await apiRejectInvoice(invoice.id, rejectionReason);
      setInvoice({ ...invoice, approval_status: 'REJECTED', rejected_reason: rejectionReason });
      toast.success(`Invoice ${invoice.invoice_number || invoice.id} rejected`);
    } catch (e: unknown) {
      toast.error(getErrorMessage(e));
    } finally {
      setActionLoading(false);
      setAction(null);
    }
  };

  const startEditing = () => {
    if (!invoice) return;
    setDraft(toEditableInvoice(invoice));
    setIsEditing(true);
  };

  const cancelEditing = () => {
    setIsEditing(false);
    setDraft(null);
  };

  const setDraftField = (field: Exclude<keyof EditableInvoice, 'line_items'>, value: string) => {
    setDraft((prev) => (prev ? { ...prev, [field]: value } : prev));
  };

  const setDraftLineItem = (index: number, field: keyof EditableLineItem, value: string) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const line_items = [...prev.line_items];
      line_items[index] = { ...line_items[index], [field]: value };
      return { ...prev, line_items };
    });
  };

  const addDraftLineItem = () => {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        line_items: [...prev.line_items, { description: '', quantity: '', unit_price: '', total: '' }],
      };
    });
  };

  const removeDraftLineItem = (index: number) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return { ...prev, line_items: prev.line_items.filter((_, i) => i !== index) };
    });
  };

  const handleSaveEdits = async () => {
    if (!invoice || !draft) return;
    setSavingEdits(true);
    try {
      const updated = await apiPatchInvoice(invoice.id, toPatchPayload(draft));
      setInvoice(updated);
      setIsEditing(false);
      setDraft(null);
      toast.success(`Invoice ${updated.invoice_number || updated.id} updated`);
    } catch (e: unknown) {
      toast.error(getErrorMessage(e));
    } finally {
      setSavingEdits(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!invoice) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3">
        <Receipt size={40} className="text-muted-foreground" />
        <h2 className="text-base font-semibold text-foreground">Invoice not found</h2>
        <button onClick={() => navigate('/invoices')} className="text-xs text-primary hover:underline">Back to Invoices</button>
      </div>
    );
  }

  const status = mapStatus(invoice.approval_status);
  const statusColors = { Pending: 'bg-warning', Approved: 'bg-success', Rejected: 'bg-destructive' };
  const cur = invoice.currency || '';

  // Validation issues map: field → issue
  const validationIssues: ValidationIssue[] = ((invoice.full_json || {}) as { validation_issues?: ValidationIssue[] }).validation_issues ?? [];
  const issueMap: Record<string, ValidationIssue> = Object.fromEntries(validationIssues.map(i => [i.field, i]));
  const hasIssues = validationIssues.length > 0;

  const subtotal = invoice.subtotal ?? invoice.line_items.reduce((s, li) => s + (li.quantity ?? 0) * (li.unit_price ?? 0), 0);
  const tax = invoice.tax_amount ?? 0;

  const hasSenderBank = invoice.sender_bank_name || invoice.sender_bank_iban || invoice.sender_bank_account_number || invoice.sender_bank_swift;
  const hasReceiverBank = invoice.receiver_bank_name || invoice.receiver_bank_iban || invoice.receiver_bank_account_number;
  const container = { hidden: {}, show: { transition: { staggerChildren: 0.06 } } };
  const item = { hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } };

  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}
      className="max-w-5xl mx-auto p-4 md:p-6">
      <div className="flex items-center gap-3 mb-5">
        <button onClick={() => navigate('/invoices')} className="p-1.5 rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition-all">
          <ArrowLeft size={16} />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="text-lg font-bold text-foreground">{invoice.invoice_number || 'Invoice'}</h1>
            <StatusBadge status={status} />
            {hasIssues && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-600 text-[10px] font-medium border border-amber-500/30">
                ⚠ {validationIssues.length} calc {validationIssues.length === 1 ? 'fix' : 'fixes'} applied
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">From {invoice.sender_name || invoice.file_name || '—'}</p>
        </div>
        <div className="flex items-center gap-2">
          {isEditing ? (
            <>
              <button
                onClick={cancelEditing}
                disabled={savingEdits}
                className="h-8 px-3 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-muted transition-all disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveEdits}
                disabled={savingEdits}
                className="h-8 px-3 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-all inline-flex items-center gap-1.5 disabled:opacity-50"
              >
                {savingEdits ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} Save Changes
              </button>
            </>
          ) : (
            <button
              onClick={startEditing}
              className="h-8 px-3 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-muted transition-all inline-flex items-center gap-1.5"
            >
              <Pencil size={12} /> Edit Invoice
            </button>
          )}
        </div>
      </div>

      <div className={`h-1 ${statusColors[status]} rounded-full mb-5`} />

      <motion.div variants={container} initial="hidden" animate="show" className="space-y-5">
        {isEditing && draft && (
          <motion.div variants={item} className="border border-border rounded-xl overflow-hidden bg-background">
            <div className="px-4 py-3 border-b border-border">
              <h3 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Edit Invoice</h3>
            </div>
            <div className="p-4 space-y-5">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                <EditField label="Invoice #" value={draft.invoice_number} onChange={(v) => setDraftField('invoice_number', v)} />
                <EditField label="Issue Date" type="date" value={draft.invoice_date} onChange={(v) => setDraftField('invoice_date', v)} />
                <EditField label="Due Date" type="date" value={draft.due_date} onChange={(v) => setDraftField('due_date', v)} />
                <EditField label="Payment Terms" value={draft.payment_terms} onChange={(v) => setDraftField('payment_terms', v)} />
                <EditField label="PO Number" value={draft.purchase_order} onChange={(v) => setDraftField('purchase_order', v)} />
                <EditField label="Currency" value={draft.currency} onChange={(v) => setDraftField('currency', v)} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="space-y-3">
                  <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Supplier</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <EditField label="Name" value={draft.sender_name} onChange={(v) => setDraftField('sender_name', v)} />
                    <EditField label="Email" type="email" value={draft.sender_email} onChange={(v) => setDraftField('sender_email', v)} />
                    <EditField label="Phone" value={draft.sender_phone} onChange={(v) => setDraftField('sender_phone', v)} />
                    <EditField label="Tax ID" value={draft.sender_tax_id} onChange={(v) => setDraftField('sender_tax_id', v)} />
                    <EditField label="City" value={draft.sender_city} onChange={(v) => setDraftField('sender_city', v)} />
                    <EditField label="Country" value={draft.sender_country} onChange={(v) => setDraftField('sender_country', v)} />
                  </div>
                  <EditTextArea label="Address" value={draft.sender_address} onChange={(v) => setDraftField('sender_address', v)} rows={2} />
                </div>

                <div className="space-y-3">
                  <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Financials</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <EditField label="Subtotal" type="number" value={draft.subtotal} onChange={(v) => setDraftField('subtotal', v)} />
                    <EditField label="Tax Rate (%)" type="number" value={draft.tax_rate} onChange={(v) => setDraftField('tax_rate', v)} />
                    <EditField label="Tax Amount" type="number" value={draft.tax_amount} onChange={(v) => setDraftField('tax_amount', v)} />
                    <EditField label="Total" type="number" value={draft.total_amount} onChange={(v) => setDraftField('total_amount', v)} />
                    <EditField label="Amount Paid" type="number" value={draft.amount_paid} onChange={(v) => setDraftField('amount_paid', v)} />
                    <EditField label="Amount Due" type="number" value={draft.amount_due} onChange={(v) => setDraftField('amount_due', v)} />
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="space-y-3">
                  <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Sender Bank</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <EditField label="Bank" value={draft.sender_bank_name} onChange={(v) => setDraftField('sender_bank_name', v)} />
                    <EditField label="Account No." value={draft.sender_bank_account_number} onChange={(v) => setDraftField('sender_bank_account_number', v)} />
                    <EditField label="IBAN" value={draft.sender_bank_iban} onChange={(v) => setDraftField('sender_bank_iban', v)} />
                    <EditField label="SWIFT / BIC" value={draft.sender_bank_swift} onChange={(v) => setDraftField('sender_bank_swift', v)} />
                  </div>
                </div>
                <div className="space-y-3">
                  <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Receiver Bank</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <EditField label="Bank" value={draft.receiver_bank_name} onChange={(v) => setDraftField('receiver_bank_name', v)} />
                    <EditField label="Account No." value={draft.receiver_bank_account_number} onChange={(v) => setDraftField('receiver_bank_account_number', v)} />
                    <EditField label="IBAN" value={draft.receiver_bank_iban} onChange={(v) => setDraftField('receiver_bank_iban', v)} />
                    <EditField label="SWIFT / BIC" value={draft.receiver_bank_swift} onChange={(v) => setDraftField('receiver_bank_swift', v)} />
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Line Items</h4>
                  <button
                    onClick={addDraftLineItem}
                    className="h-7 px-2.5 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-muted transition-all inline-flex items-center gap-1"
                  >
                    <Plus size={12} /> Add Line
                  </button>
                </div>
                <div className="overflow-x-auto border border-border rounded-lg">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-surface-2 text-muted-foreground">
                        <th className="px-3 py-2 text-left font-medium">Description</th>
                        <th className="px-3 py-2 text-right font-medium w-28">Qty</th>
                        <th className="px-3 py-2 text-right font-medium w-32">Unit Price</th>
                        <th className="px-3 py-2 text-right font-medium w-32">Total</th>
                        <th className="px-3 py-2 text-center font-medium w-16">-</th>
                      </tr>
                    </thead>
                    <tbody>
                      {draft.line_items.length === 0 && (
                        <tr>
                          <td colSpan={5} className="px-3 py-3 text-center text-muted-foreground">No line items</td>
                        </tr>
                      )}
                      {draft.line_items.map((li, i) => (
                        <tr key={`${i}-${li.description}`} className="border-t border-border">
                          <td className="px-3 py-2">
                            <input
                              value={li.description}
                              onChange={(e) => setDraftLineItem(i, 'description', e.target.value)}
                              className="h-8 w-full rounded-md border border-border bg-background px-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
                              placeholder="Description"
                            />
                          </td>
                          <td className="px-3 py-2">
                            <input
                              type="number"
                              value={li.quantity}
                              onChange={(e) => setDraftLineItem(i, 'quantity', e.target.value)}
                              className="h-8 w-full rounded-md border border-border bg-background px-2 text-xs text-foreground text-right focus:outline-none focus:ring-2 focus:ring-primary/30"
                              placeholder="0"
                            />
                          </td>
                          <td className="px-3 py-2">
                            <input
                              type="number"
                              value={li.unit_price}
                              onChange={(e) => setDraftLineItem(i, 'unit_price', e.target.value)}
                              className="h-8 w-full rounded-md border border-border bg-background px-2 text-xs text-foreground text-right focus:outline-none focus:ring-2 focus:ring-primary/30"
                              placeholder="0.00"
                            />
                          </td>
                          <td className="px-3 py-2">
                            <input
                              type="number"
                              value={li.total}
                              onChange={(e) => setDraftLineItem(i, 'total', e.target.value)}
                              className="h-8 w-full rounded-md border border-border bg-background px-2 text-xs text-foreground text-right focus:outline-none focus:ring-2 focus:ring-primary/30"
                              placeholder="0.00"
                            />
                          </td>
                          <td className="px-3 py-2 text-center">
                            <button
                              onClick={() => removeDraftLineItem(i)}
                              className="h-7 w-7 rounded-md border border-border text-muted-foreground hover:text-destructive hover:border-destructive/30 hover:bg-destructive/5 inline-flex items-center justify-center transition-all"
                            >
                              <Trash2 size={12} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <EditTextArea label="Notes" value={draft.notes} onChange={(v) => setDraftField('notes', v)} rows={3} />
            </div>
          </motion.div>
        )}

        {/* Supplier + Invoice Details */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <motion.div variants={item} className="border border-border rounded-xl p-4 bg-background">
            <h3 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-3">Supplier</h3>
            <div className="flex items-center gap-3 mb-3">
              <div className="w-9 h-9 rounded-lg bg-primary/15 flex items-center justify-center text-primary font-semibold text-xs flex-shrink-0">
                {(invoice.sender_name || 'UN').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground truncate">{invoice.sender_name || '—'}</p>
                <p className="text-[11px] text-muted-foreground truncate">{invoice.sender_email || '—'}</p>
              </div>
            </div>
            <div className="space-y-2">
              <DetailRow icon={MapPin} label="Address" value={[invoice.sender_address, invoice.sender_city, invoice.sender_country].filter(Boolean).join(', ') || '—'} />
              <DetailRow icon={Phone} label="Phone" value={invoice.sender_phone || '—'} />
              <DetailRow icon={Hash} label="Tax ID" value={invoice.sender_tax_id || '—'} />
            </div>
          </motion.div>

          <motion.div variants={item} className="border border-border rounded-xl p-4 bg-background">
            <h3 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-3">Invoice Details</h3>
            <div className="space-y-2">
              <DetailRow icon={Receipt} label="Invoice #" value={invoice.invoice_number || '—'} />
              <DetailRow icon={Calendar} label="Issue Date" value={invoice.invoice_date || '—'} />
              <DetailRow icon={Calendar} label="Due Date" value={invoice.due_date || '—'} />
              <DetailRow icon={Clock} label="Payment Terms" value={invoice.payment_terms || '—'} />
              <DetailRow icon={CreditCard} label="PO Number" value={invoice.purchase_order || '—'} />
              <DetailRow icon={Mail} label="Source" value={invoice.source || 'upload'} />
            </div>
          </motion.div>
        </div>

        {/* Line Items */}
        <motion.div variants={item} className="border border-border rounded-xl overflow-hidden bg-background">
          <div className="px-4 py-3 border-b border-border">
            <h3 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Line Items</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-surface-2 text-muted-foreground">
                  <th className="px-4 py-2.5 text-left font-medium w-8">#</th>
                  <th className="px-4 py-2.5 text-left font-medium">Description</th>
                  <th className="px-4 py-2.5 text-right font-medium">Qty</th>
                  <th className="px-4 py-2.5 text-right font-medium">Unit Price</th>
                  <th className="px-4 py-2.5 text-right font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                {invoice.line_items.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-4 text-center text-muted-foreground">No line items</td></tr>
                )}
                {invoice.line_items.map((li, i) => {
                  const liIssue = issueMap[`line_items[${i}].total`];
                  return (
                    <tr key={li.id} className={`border-t border-border ${liIssue ? 'bg-amber-500/5' : ''}`}>
                      <td className="px-4 py-2.5 text-muted-foreground">{i + 1}</td>
                      <td className="px-4 py-2.5 text-foreground">{li.description || '—'}</td>
                      <td className="px-4 py-2.5 text-right text-foreground">{li.quantity ?? '—'}</td>
                      <td className="px-4 py-2.5 text-right text-foreground">
                        {li.unit_price != null ? `${cur} ${li.unit_price.toFixed(2)}` : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right font-medium text-foreground">
                        {li.total != null ? (
                          liIssue ? (
                            <span className="inline-flex items-center gap-1.5">
                              <span className="line-through text-amber-500/70 bg-amber-500/10 px-1 rounded text-[10px]" title={liIssue.note}>
                                {cur} {liIssue.original.toFixed(2)}
                              </span>
                              {cur} {li.total.toFixed(2)}
                            </span>
                          ) : `${cur} ${li.total.toFixed(2)}`
                        ) : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className={`border-t border-border ${issueMap['subtotal'] ? 'bg-amber-500/5' : ''}`}>
                  <td colSpan={4} className="px-4 py-2 text-right text-muted-foreground">Subtotal</td>
                  <td className="px-4 py-2 text-right text-foreground">
                    <ValCell field="subtotal" value={invoice.subtotal ?? subtotal} currency={cur} issueMap={issueMap} />
                  </td>
                </tr>
                <tr className={issueMap['tax_amount'] ? 'bg-amber-500/5' : ''}>
                  <td colSpan={4} className="px-4 py-2 text-right text-muted-foreground">Tax ({invoice.tax_rate ?? 0}%)</td>
                  <td className="px-4 py-2 text-right text-foreground">
                    <ValCell field="tax_amount" value={invoice.tax_amount ?? tax} currency={cur} issueMap={issueMap} />
                  </td>
                </tr>
                <tr className={`border-t border-border font-semibold ${issueMap['total_amount'] ? 'bg-amber-500/5' : ''}`}>
                  <td colSpan={4} className="px-4 py-2.5 text-right text-foreground">Total</td>
                  <td className="px-4 py-2.5 text-right text-foreground text-sm">
                    <ValCell field="total_amount" value={invoice.total_amount ?? subtotal + tax} currency={cur} issueMap={issueMap} />
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </motion.div>

        {/* Bank Details */}
        {(hasSenderBank || hasReceiverBank) && (
          <motion.div variants={item} className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {hasSenderBank && (
              <div className="border border-border rounded-xl p-4 bg-background">
                <h3 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-3">Sender Bank (Payment To)</h3>
                <div className="space-y-1.5">
                  {invoice.sender_bank_name && <BankRow label="Bank" value={invoice.sender_bank_name} />}
                  {invoice.sender_bank_account_holder && <BankRow label="Account Holder" value={invoice.sender_bank_account_holder} />}
                  {invoice.sender_bank_account_number && <BankRow label="Account No." value={invoice.sender_bank_account_number} />}
                  {invoice.sender_bank_iban && <BankRow label="IBAN" value={invoice.sender_bank_iban} />}
                  {invoice.sender_bank_swift && <BankRow label="SWIFT / BIC" value={invoice.sender_bank_swift} />}
                  {invoice.sender_bank_routing && <BankRow label="Routing No." value={invoice.sender_bank_routing} />}
                  {invoice.sender_bank_sort_code && <BankRow label="Sort Code" value={invoice.sender_bank_sort_code} />}
                  {invoice.sender_bank_branch && <BankRow label="Branch" value={invoice.sender_bank_branch} />}
                </div>
              </div>
            )}
            {hasReceiverBank && (
              <div className="border border-border rounded-xl p-4 bg-background">
                <h3 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-3">Receiver Bank</h3>
                <div className="space-y-1.5">
                  {invoice.receiver_bank_name && <BankRow label="Bank" value={invoice.receiver_bank_name} />}
                  {invoice.receiver_bank_account_holder && <BankRow label="Account Holder" value={invoice.receiver_bank_account_holder} />}
                  {invoice.receiver_bank_account_number && <BankRow label="Account No." value={invoice.receiver_bank_account_number} />}
                  {invoice.receiver_bank_iban && <BankRow label="IBAN" value={invoice.receiver_bank_iban} />}
                  {invoice.receiver_bank_swift && <BankRow label="SWIFT / BIC" value={invoice.receiver_bank_swift} />}
                  {invoice.receiver_bank_routing && <BankRow label="Routing No." value={invoice.receiver_bank_routing} />}
                  {invoice.receiver_bank_sort_code && <BankRow label="Sort Code" value={invoice.receiver_bank_sort_code} />}
                </div>
              </div>
            )}
          </motion.div>
        )}

        {/* Financial Summary */}
        <motion.div variants={item} className="border border-border rounded-xl overflow-hidden bg-background">
          <div className="px-4 py-3 border-b border-border">
            <h3 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Financial Summary</h3>
          </div>
          <div className="p-4 flex justify-end">
            <table style={{ width: 320, borderCollapse: 'collapse' }}>
              {invoice.subtotal != null && (
                <FinRow label="Subtotal" field="subtotal" value={invoice.subtotal} currency={cur} issueMap={issueMap} />
              )}
              {(invoice.discount_total ?? 0) > 0 && (
                <FinRow label={`Discount${invoice.discount_percent ? ` (${invoice.discount_percent}%)` : ''}`}
                  field="discount_total" value={invoice.discount_total} currency={cur} issueMap={issueMap} prefix="- " />
              )}
              {invoice.tax_amount != null && (
                <FinRow label={`${invoice.tax_type || 'Tax'}${invoice.tax_rate ? ` (${invoice.tax_rate}%)` : ''}`}
                  field="tax_amount" value={invoice.tax_amount} currency={cur} issueMap={issueMap} />
              )}
              {(invoice.shipping ?? 0) > 0 && (
                <FinRow label="Shipping" field="shipping" value={invoice.shipping} currency={cur} issueMap={issueMap} />
              )}
              {(invoice.handling ?? 0) > 0 && (
                <FinRow label="Handling" field="handling" value={invoice.handling} currency={cur} issueMap={issueMap} />
              )}
              {(invoice.other_charges ?? 0) > 0 && (
                <FinRow label="Other Charges" field="other_charges" value={invoice.other_charges} currency={cur} issueMap={issueMap} />
              )}
              <tr className={`border-t-2 border-primary ${issueMap['total_amount'] ? 'bg-amber-500/5' : ''}`}>
                <td className="px-3 py-2.5 font-bold text-sm text-foreground">Total</td>
                <td className="px-3 py-2.5 text-right font-bold text-sm text-primary">
                  <ValCell field="total_amount" value={invoice.total_amount ?? subtotal + tax} currency={cur} issueMap={issueMap} />
                </td>
              </tr>
              {(invoice.amount_paid ?? 0) > 0 && (
                <FinRow label="Amount Paid" field="amount_paid" value={invoice.amount_paid} currency={cur} issueMap={issueMap} />
              )}
              {(invoice.deposit ?? 0) > 0 && (
                <FinRow label="Deposit" field="deposit" value={invoice.deposit} currency={cur} issueMap={issueMap} />
              )}
              {invoice.amount_due != null && (
                <tr className={`${issueMap['amount_due'] ? 'bg-amber-500/10' : 'bg-warning/10'}`}>
                  <td className="px-3 py-2 font-semibold text-xs text-warning">Amount Due</td>
                  <td className="px-3 py-2 text-right font-semibold text-xs text-warning">
                    <ValCell field="amount_due" value={invoice.amount_due} currency={cur} issueMap={issueMap} />
                  </td>
                </tr>
              )}
            </table>
          </div>
        </motion.div>

        {invoice.notes && (
          <motion.div variants={item} className="border border-border rounded-xl p-4 bg-background">
            <h3 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Notes</h3>
            <p className="text-xs text-foreground bg-surface-2 p-3 rounded-lg">{invoice.notes}</p>
          </motion.div>
        )}

        {status === 'Approved' && (
          <motion.div variants={item} className="p-3 rounded-xl bg-success/10 border border-success/20 text-success text-xs">
            ✅ Approved by {invoice.approved_by || 'user'} on {invoice.approved_at?.split('T')[0] || '—'}
          </motion.div>
        )}
        {status === 'Rejected' && (
          <motion.div variants={item} className="p-3 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-xs">
            ❌ Rejected by {invoice.approved_by || 'user'} on {invoice.approved_at?.split('T')[0] || '—'}
            {invoice.rejected_reason && <p className="mt-1 opacity-80">Reason: {invoice.rejected_reason}</p>}
          </motion.div>
        )}

        {status === 'Pending' && (
          <motion.div variants={item} className="border border-border rounded-xl p-4 bg-background">
            <div className="p-3 rounded-lg bg-warning/10 border border-warning/20 text-warning text-xs mb-4">
              ⏳ This invoice is awaiting your review and approval.
            </div>
            {action === 'reject' ? (
              <div className="space-y-3">
                <textarea value={rejectionReason} onChange={e => setRejectionReason(e.target.value)}
                  placeholder="Reason for rejection (optional)" rows={3}
                  className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-destructive" />
                <div className="flex gap-2">
                  <button onClick={() => setAction(null)} className="px-3 h-8 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-muted transition-all">Cancel</button>
                  <button onClick={handleReject} disabled={actionLoading}
                    className="px-3 h-8 rounded-lg bg-destructive text-destructive-foreground text-xs font-medium hover:bg-destructive/90 transition-all flex items-center gap-1.5 disabled:opacity-50">
                    {actionLoading ? <Loader2 size={12} className="animate-spin" /> : <XCircle size={12} />} Confirm Rejection
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex gap-3">
                <button onClick={handleApprove} disabled={actionLoading}
                  className="flex-1 h-9 rounded-lg bg-success text-success-foreground text-xs font-medium hover:bg-success/90 transition-all flex items-center justify-center gap-1.5 disabled:opacity-50">
                  {actionLoading ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle size={12} />} Approve Invoice
                </button>
                <button onClick={() => setAction('reject')}
                  className="flex-1 h-9 rounded-lg border border-destructive text-destructive text-xs font-medium hover:bg-destructive/10 transition-all flex items-center justify-center gap-1.5">
                  <XCircle size={12} /> Reject Invoice
                </button>
              </div>
            )}
          </motion.div>
        )}
      </motion.div>
    </motion.div>
  );
}

function EditField({ label, value, onChange, type = 'text' }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <label className="space-y-1 block">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 w-full rounded-lg border border-border bg-surface-2 px-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
      />
    </label>
  );
}

function EditTextArea({ label, value, onChange, rows = 2 }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
}) {
  return (
    <label className="space-y-1 block">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        className="w-full rounded-lg border border-border bg-surface-2 px-2.5 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
      />
    </label>
  );
}

function DetailRow({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="flex items-start gap-2.5">
      <Icon size={13} className="text-muted-foreground mt-0.5 flex-shrink-0" />
      <div className="min-w-0">
        <span className="text-[11px] text-muted-foreground">{label}</span>
        <p className="text-xs text-foreground">{value}</p>
      </div>
    </div>
  );
}

function BankRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1 border-b border-border/50 last:border-0">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className="text-xs text-foreground font-mono">{value}</span>
    </div>
  );
}

function FinRow({ label, field, value, currency = '', issueMap, prefix = '' }: {
  label: string;
  field: string;
  value: number | null | undefined;
  currency?: string;
  issueMap: Record<string, ValidationIssue>;
  prefix?: string;
}) {
  const issue = issueMap[field];
  const fmt = (n: number) => `${prefix}${currency} ${n.toFixed(2)}`.trim();
  return (
    <tr className={issue ? 'bg-amber-500/5' : ''}>
      <td className="px-3 py-1.5 text-xs text-muted-foreground">{label}</td>
      <td className="px-3 py-1.5 text-right text-xs text-foreground">
        {value == null ? '—' : issue ? (
          <span className="inline-flex items-center gap-1.5">
            <span className="line-through text-amber-500/70 bg-amber-500/10 px-1 rounded text-[10px]" title={issue.note}>
              {fmt(issue.original)}
            </span>
            {fmt(value)}
          </span>
        ) : fmt(value)}
      </td>
    </tr>
  );
}


