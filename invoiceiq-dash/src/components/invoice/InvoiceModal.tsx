import { useState } from 'react';
import { motion } from 'framer-motion';
import { X, CheckCircle, XCircle, Loader2, FileText } from 'lucide-react';
import { Invoice } from '@/data/mockInvoices';
import { StatusBadge } from './StatusBadge';
import { toast } from 'sonner';

interface Props {
  invoice: Invoice;
  onClose: () => void;
  onUpdate: (invoice: Invoice) => void;
}

export function InvoiceModal({ invoice, onClose, onUpdate }: Props) {
  const [action, setAction] = useState<'approve' | 'reject' | null>(null);
  const [loading, setLoading] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');

  const handleApprove = async () => {
    setLoading(true);
    await new Promise(r => setTimeout(r, 1000));
    const updated: Invoice = {
      ...invoice,
      status: 'Approved',
      approvedBy: 'Admin User',
      approvedAt: new Date().toISOString().split('T')[0],
    };
    onUpdate(updated);
    toast.success(`Invoice ${invoice.invoiceNumber} approved`);
  };

  const handleReject = async () => {
    setLoading(true);
    await new Promise(r => setTimeout(r, 1000));
    const updated: Invoice = {
      ...invoice,
      status: 'Rejected',
      rejectedBy: 'Admin User',
      rejectedAt: new Date().toISOString().split('T')[0],
      rejectionReason: rejectionReason || undefined,
    };
    onUpdate(updated);
    toast.success(`Invoice ${invoice.invoiceNumber} rejected`);
  };

  const subtotal = invoice.lineItems.reduce((s, li) => s + li.quantity * li.unitPrice, 0);
  const tax = invoice.lineItems.reduce((s, li) => s + li.quantity * li.unitPrice * li.taxPercent / 100, 0);

  const statusColors = {
    Pending: 'bg-warning',
    Approved: 'bg-success',
    Rejected: 'bg-destructive',
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-foreground/20 backdrop-blur-sm" />
      <motion.div
        initial={{ scale: 0.92, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.92, opacity: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 25 }}
        className="relative bg-background border border-border rounded-xl shadow-xl w-full max-w-2xl max-h-[85vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        {/* Header strip */}
        <div className={`h-1.5 ${statusColors[invoice.status]} rounded-t-xl`} />

        <div className="p-6">
          {/* Top */}
          <div className="flex items-start justify-between mb-6">
            <div>
              <div className="flex items-center gap-3">
                <h2 className="text-xl font-bold text-foreground">{invoice.invoiceNumber}</h2>
                <StatusBadge status={invoice.status} />
              </div>
              <p className="text-muted-foreground text-sm mt-1">Invoice from {invoice.vendor}</p>
            </div>
            <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition-all">
              <X size={18} />
            </button>
          </div>

          {/* Two column info */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-6">
            <div className="space-y-3">
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Supplier Info</h3>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center text-primary font-semibold text-sm">
                  {invoice.vendor.split(' ').map(w => w[0]).join('').slice(0, 2)}
                </div>
                <div>
                  <p className="font-medium text-foreground">{invoice.vendor}</p>
                  <p className="text-xs text-muted-foreground">{invoice.vendorEmail}</p>
                </div>
              </div>
              <InfoRow label="Address" value={invoice.vendorAddress} />
              <InfoRow label="Phone" value={invoice.vendorPhone} />
              <InfoRow label="Tax ID" value={invoice.vendorTaxId} />
            </div>
            <div className="space-y-3">
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Invoice Details</h3>
              <InfoRow label="Invoice #" value={invoice.invoiceNumber} />
              <InfoRow label="Issue Date" value={invoice.issueDate} />
              <InfoRow label="Due Date" value={invoice.dueDate} />
              <InfoRow label="Payment Terms" value={invoice.paymentTerms} />
              <InfoRow label="PO Number" value={invoice.poNumber} />
              <InfoRow label="Received Via" value="Email" />
            </div>
          </div>

          {/* Line items */}
          <div className="mb-6">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Line Items</h3>
            <div className="border border-border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-surface-2 text-muted-foreground">
                    <th className="px-3 py-2 text-left font-medium">#</th>
                    <th className="px-3 py-2 text-left font-medium">Description</th>
                    <th className="px-3 py-2 text-right font-medium">Qty</th>
                    <th className="px-3 py-2 text-right font-medium">Unit Price</th>
                    <th className="px-3 py-2 text-right font-medium">Tax %</th>
                    <th className="px-3 py-2 text-right font-medium">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {invoice.lineItems.map((li, i) => (
                    <tr key={li.id} className="border-t border-border">
                      <td className="px-3 py-2 text-muted-foreground">{i + 1}</td>
                      <td className="px-3 py-2 text-foreground">{li.description}</td>
                      <td className="px-3 py-2 text-right text-foreground">{li.quantity}</td>
                      <td className="px-3 py-2 text-right text-foreground">${li.unitPrice.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right text-muted-foreground">{li.taxPercent}%</td>
                      <td className="px-3 py-2 text-right font-medium text-foreground">${(li.quantity * li.unitPrice).toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-border">
                    <td colSpan={5} className="px-3 py-2 text-right text-muted-foreground">Subtotal</td>
                    <td className="px-3 py-2 text-right text-foreground">${subtotal.toFixed(2)}</td>
                  </tr>
                  <tr>
                    <td colSpan={5} className="px-3 py-2 text-right text-muted-foreground">Tax</td>
                    <td className="px-3 py-2 text-right text-foreground">${tax.toFixed(2)}</td>
                  </tr>
                  <tr className="border-t border-border font-semibold">
                    <td colSpan={5} className="px-3 py-2 text-right text-foreground">Total</td>
                    <td className="px-3 py-2 text-right text-foreground">${(subtotal + tax).toFixed(2)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>

          {/* Notes */}
          {invoice.notes && (
            <div className="mb-6">
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Notes</h3>
              <p className="text-sm text-foreground bg-surface-2 p-3 rounded-lg">{invoice.notes}</p>
            </div>
          )}

          {/* Attachment */}
          <div className="flex items-center gap-2 mb-6 text-sm text-muted-foreground">
            <FileText size={14} />
            <span>invoice_{invoice.vendor.toLowerCase().replace(/\s+/g, '_')}_2024.pdf 📎</span>
          </div>

          {/* Approval info for non-pending */}
          {invoice.status === 'Approved' && (
            <div className="p-3 rounded-lg bg-success/10 border border-success/20 text-success text-sm">
              Approved by {invoice.approvedBy} on {invoice.approvedAt}
            </div>
          )}
          {invoice.status === 'Rejected' && (
            <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
              Rejected by {invoice.rejectedBy} on {invoice.rejectedAt}
              {invoice.rejectionReason && <p className="mt-1 opacity-80">Reason: {invoice.rejectionReason}</p>}
            </div>
          )}

          {/* Actions for pending */}
          {invoice.status === 'Pending' && (
            <div className="mt-6 pt-6 border-t border-border">
              <div className="p-3 rounded-lg bg-warning/10 border border-warning/20 text-warning text-sm mb-4">
                This invoice is awaiting your review and approval.
              </div>

              {action === 'reject' ? (
                <div className="space-y-3">
                  <textarea
                    value={rejectionReason}
                    onChange={e => setRejectionReason(e.target.value)}
                    placeholder="Reason for rejection (optional)"
                    rows={3}
                    className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-destructive"
                  />
                  <div className="flex gap-2">
                    <button onClick={() => setAction(null)} className="px-4 h-10 rounded-lg border border-border text-sm font-medium text-foreground hover:bg-muted transition-all">
                      Cancel
                    </button>
                    <button onClick={handleReject} disabled={loading} className="px-4 h-10 rounded-lg bg-destructive text-destructive-foreground text-sm font-medium hover:bg-destructive/90 transition-all flex items-center gap-2 disabled:opacity-50">
                      {loading ? <Loader2 size={14} className="animate-spin" /> : <XCircle size={14} />}
                      Confirm Rejection
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex gap-3">
                  <button
                    onClick={handleApprove}
                    disabled={loading}
                    className="flex-1 h-11 rounded-lg bg-success text-success-foreground text-sm font-medium hover:bg-success/90 transition-all flex items-center justify-center gap-2 active:scale-[0.97] disabled:opacity-50"
                  >
                    {loading && action === 'approve' ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle size={14} />}
                    Approve Invoice
                  </button>
                  <button
                    onClick={() => setAction('reject')}
                    className="flex-1 h-11 rounded-lg border border-destructive text-destructive text-sm font-medium hover:bg-destructive/10 transition-all flex items-center justify-center gap-2 active:scale-[0.97]"
                  >
                    <XCircle size={14} /> Reject Invoice
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-xs text-muted-foreground">{label}</span>
      <p className="text-sm text-foreground">{value}</p>
    </div>
  );
}
