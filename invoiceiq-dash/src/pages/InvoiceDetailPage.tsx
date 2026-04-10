import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, CheckCircle, XCircle, Loader2, MapPin, Phone, Hash, Clock, Receipt, Calendar, CreditCard, Mail } from 'lucide-react';
import { apiGetInvoice, apiApproveInvoice, apiRejectInvoice, RealInvoice } from '@/lib/api';
import { StatusBadge } from '@/components/invoice/StatusBadge';
import { toast } from 'sonner';

function mapStatus(s: string): 'Pending' | 'Approved' | 'Rejected' {
  if (s === 'APPROVED') return 'Approved';
  if (s === 'REJECTED') return 'Rejected';
  return 'Pending';
}

type ValidationIssue = { field: string; original: number; corrected: number; note: string };

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
    } catch (e: any) {
      toast.error(e.message);
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
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setActionLoading(false);
      setAction(null);
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
  const validationIssues: ValidationIssue[] = (invoice.full_json as any)?.validation_issues ?? [];
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
      </div>

      <div className={`h-1 ${statusColors[status]} rounded-full mb-5`} />

      <motion.div variants={container} initial="hidden" animate="show" className="space-y-5">
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


