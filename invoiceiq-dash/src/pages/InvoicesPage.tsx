import { useState, useMemo, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Eye, ChevronLeft, ChevronRight, RefreshCw, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiGetInvoices, apiDeleteInvoice, RealInvoice } from '@/lib/api';
import { StatusBadge } from '@/components/invoice/StatusBadge';
import { toast } from 'sonner';

const statusFilters = ['All', 'PENDING', 'APPROVED', 'REJECTED'] as const;
const ROWS_PER_PAGE = 8;

function mapStatus(s: string): 'Pending' | 'Approved' | 'Rejected' {
  if (s === 'APPROVED') return 'Approved';
  if (s === 'REJECTED') return 'Rejected';
  return 'Pending';
}

export default function InvoicesPage() {
  const navigate = useNavigate();
  const [invoices, setInvoices] = useState<RealInvoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('All');
  const [sortField, setSortField] = useState<string>('');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [currentPage, setCurrentPage] = useState(1);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this invoice? This cannot be undone.')) return;
    setDeletingId(id);
    try {
      await apiDeleteInvoice(id);
      setInvoices(prev => prev.filter(inv => inv.id !== id));
      toast.success('Invoice deleted');
    } catch (err: any) {
      toast.error(err.message);
    }
    setDeletingId(null);
  };

  const load = async () => {
    setLoading(true);
    try {
      const data = await apiGetInvoices();
      setInvoices(data);
    } catch (e) {
      console.error('Failed to load invoices', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const stats = useMemo(() => ({
    total: invoices.length,
    pending: invoices.filter(i => i.approval_status === 'PENDING').length,
    approved: invoices.filter(i => i.approval_status === 'APPROVED').length,
    rejected: invoices.filter(i => i.approval_status === 'REJECTED').length,
  }), [invoices]);

  const filtered = useMemo(() => {
    let result = [...invoices];
    if (statusFilter !== 'All') result = result.filter(i => i.approval_status === statusFilter);
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(i =>
        (i.invoice_number || '').toLowerCase().includes(q) ||
        (i.sender_name || '').toLowerCase().includes(q) ||
        (i.receiver_name || '').toLowerCase().includes(q)
      );
    }
    if (sortField) {
      result.sort((a, b) => {
        const aVal = (a as any)[sortField] ?? '';
        const bVal = (b as any)[sortField] ?? '';
        if (typeof aVal === 'number' && typeof bVal === 'number')
          return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
        return sortDir === 'asc'
          ? String(aVal).localeCompare(String(bVal))
          : String(bVal).localeCompare(String(aVal));
      });
    }
    return result;
  }, [invoices, statusFilter, search, sortField, sortDir]);

  useMemo(() => setCurrentPage(1), [statusFilter, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / ROWS_PER_PAGE));
  const paginated = filtered.slice((currentPage - 1) * ROWS_PER_PAGE, currentPage * ROWS_PER_PAGE);

  const handleSort = (field: string) => {
    if (sortField === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortField(field); setSortDir('asc'); }
  };

  const getPageNumbers = () => {
    const pages: (number | 'ellipsis')[] = [];
    if (totalPages <= 5) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
      pages.push(1);
      if (currentPage > 3) pages.push('ellipsis');
      for (let i = Math.max(2, currentPage - 1); i <= Math.min(totalPages - 1, currentPage + 1); i++) pages.push(i);
      if (currentPage < totalPages - 2) pages.push('ellipsis');
      pages.push(totalPages);
    }
    return pages;
  };

  const formatProcessedDate = (createdAt?: string | null) => {
    if (!createdAt) return '—';

    const d = new Date(createdAt);
    if (Number.isNaN(d.getTime())) return '—';

    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">Loading invoices...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div>
          <h1 className="text-lg font-bold text-foreground">Invoice Processing</h1>
          <p className="text-muted-foreground text-xs mt-0.5">Review, approve, and manage all incoming invoices</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          {[
            { label: 'Total', value: stats.total, color: 'text-foreground' },
            { label: 'Pending', value: stats.pending, color: 'text-warning' },
            { label: 'Approved', value: stats.approved, color: 'text-success' },
            { label: 'Rejected', value: stats.rejected, color: 'text-destructive' },
          ].map((s, i) => (
            <motion.div key={s.label} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
              className="px-2.5 py-1 rounded-lg bg-surface-2 border border-border">
              <span className="text-[11px] text-muted-foreground">{s.label}: </span>
              <span className={`text-xs font-semibold ${s.color}`}>{s.value}</span>
            </motion.div>
          ))}
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-2 mb-3">
        <div className="relative flex-1 max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search invoices..."
            className="w-full rounded-lg border border-border bg-surface-2 pl-8 pr-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition-all" />
        </div>
        <div className="flex gap-0.5 bg-surface-2 rounded-lg p-0.5 border border-border">
          {statusFilters.map(s => (
            <button key={s} onClick={() => setStatusFilter(s)}
              className={`px-2.5 py-1.5 rounded-md text-xs font-medium transition-all relative ${statusFilter === s ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
              {statusFilter === s && <motion.div layoutId="filter-pill" className="absolute inset-0 bg-background rounded-md border border-border shadow-sm" />}
              <span className="relative z-10">{s === 'PENDING' ? 'Pending' : s === 'APPROVED' ? 'Approved' : s === 'REJECTED' ? 'Rejected' : s}</span>
            </button>
          ))}
        </div>
        <button onClick={load} className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-muted transition-all">
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      <div className="hidden md:block border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-surface-2 text-muted-foreground">
                {[
                  { key: 'invoice_number', label: 'Invoice #' },
                  { key: 'created_at', label: 'Processed Date' },
                  { key: 'sender_name', label: 'Vendor' },
                  { key: 'receiver_name', label: 'Bill To' },
                  { key: 'invoice_date', label: 'Issue Date' },
                  { key: 'due_date', label: 'Due Date' },
                  { key: 'total_amount', label: 'Amount' },
                  { key: 'approval_status', label: 'Status' },
                ].map(col => (
                  <th key={col.key} onClick={() => handleSort(col.key)}
                    className="px-3 py-2.5 text-left font-medium cursor-pointer hover:text-foreground transition-colors select-none text-[11px]">
                    {col.label}{sortField === col.key && <span className="ml-1">{sortDir === 'asc' ? '↑' : '↓'}</span>}
                  </th>
                ))}
                <th className="px-3 py-2.5 text-left font-medium text-[11px]">Actions</th>
              </tr>
            </thead>
            <tbody>
              {paginated.map((inv, i) => (
                <motion.tr key={inv.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}
                  className="border-t border-border hover:bg-surface-2 transition-colors">
                  <td className="px-3 py-2.5 font-medium text-foreground">{inv.invoice_number || '—'}</td>
                  <td className="px-3 py-2.5 font-medium text-foreground">{formatProcessedDate(inv.created_at)}</td>
                  <td className="px-3 py-2.5 text-foreground">{inv.sender_name || '—'}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{inv.receiver_name || '—'}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{inv.invoice_date || '—'}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{inv.due_date || '—'}</td>
                  <td className="px-3 py-2.5 font-medium text-foreground">
                    {inv.total_amount != null ? `${inv.currency || ''} ${inv.total_amount.toFixed(2)}` : '—'}
                  </td>
                  <td className="px-3 py-2.5"><StatusBadge status={mapStatus(inv.approval_status)} /></td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-1">
                      <button onClick={() => navigate(`/invoices/${inv.id}`)}
                        className="flex items-center gap-1 px-2 py-1 rounded-md border border-border text-[11px] font-medium text-foreground hover:bg-muted hover:scale-105 transition-all">
                        <Eye size={11} /> View
                      </button>
                      <button onClick={(e) => handleDelete(inv.id, e)} disabled={deletingId === inv.id}
                        className="flex items-center gap-1 px-2 py-1 rounded-md border border-destructive/30 text-[11px] font-medium text-destructive hover:bg-destructive/10 transition-all disabled:opacity-50">
                        <Trash2 size={11} />
                      </button>
                    </div>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-border bg-surface-2">
            <p className="text-[11px] text-muted-foreground">
              Showing {((currentPage - 1) * ROWS_PER_PAGE) + 1}–{Math.min(currentPage * ROWS_PER_PAGE, filtered.length)} of {filtered.length}
            </p>
            <div className="flex items-center gap-1">
              <button onClick={() => setCurrentPage(p => Math.max(1, p - 1))} disabled={currentPage === 1}
                className="p-1.5 rounded-md text-muted-foreground hover:bg-muted disabled:opacity-30 transition-all">
                <ChevronLeft size={14} />
              </button>
              {getPageNumbers().map((page, idx) =>
                page === 'ellipsis' ? <span key={`e-${idx}`} className="px-1.5 text-[11px] text-muted-foreground">…</span> : (
                  <button key={page} onClick={() => setCurrentPage(page)}
                    className={`min-w-[28px] h-7 rounded-md text-[11px] font-medium transition-all ${currentPage === page ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'}`}>
                    {page}
                  </button>
                )
              )}
              <button onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages}
                className="p-1.5 rounded-md text-muted-foreground hover:bg-muted disabled:opacity-30 transition-all">
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      {filtered.length === 0 && !loading && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center py-12">
          <div className="w-12 h-12 rounded-full bg-surface-2 flex items-center justify-center mx-auto mb-3">
            <Search size={18} className="text-muted-foreground" />
          </div>
          <h3 className="text-sm font-medium text-foreground">No invoices found</h3>
          <p className="text-muted-foreground text-xs mt-1">Upload an invoice or configure email polling to get started</p>
        </motion.div>
      )}
    </div>
  );
}
