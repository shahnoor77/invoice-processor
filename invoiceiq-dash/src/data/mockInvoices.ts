export interface InvoiceLineItem {
  id: string;
  description: string;
  quantity: number;
  unitPrice: number;
  taxPercent: number;
}

export interface Invoice {
  id: string;
  invoiceNumber: string;
  vendor: string;
  vendorEmail: string;
  vendorPhone: string;
  vendorAddress: string;
  vendorTaxId: string;
  category: string;
  issueDate: string;
  dueDate: string;
  amount: number;
  status: 'Pending' | 'Approved' | 'Rejected';
  paymentTerms: string;
  poNumber: string;
  lineItems: InvoiceLineItem[];
  notes: string;
  approvedBy?: string;
  approvedAt?: string;
  rejectedBy?: string;
  rejectedAt?: string;
  rejectionReason?: string;
}

export const mockInvoices: Invoice[] = [
  {
    id: '1', invoiceNumber: 'INV-2024-001', vendor: 'Acme Corp', vendorEmail: 'billing@acme.com', vendorPhone: '+1-555-0101', vendorAddress: '123 Main St, San Francisco, CA 94102', vendorTaxId: 'US-TAX-88291', category: 'Software Subscriptions', issueDate: '2024-12-01', dueDate: '2024-12-31', amount: 2450.00, status: 'Pending', paymentTerms: 'Net 30', poNumber: 'PO-8834', notes: 'Annual license renewal for enterprise plan.',
    lineItems: [
      { id: '1a', description: 'Enterprise License - Annual', quantity: 1, unitPrice: 2000.00, taxPercent: 10 },
      { id: '1b', description: 'Premium Support Add-on', quantity: 1, unitPrice: 450.00, taxPercent: 10 },
    ],
  },
  {
    id: '2', invoiceNumber: 'INV-2024-002', vendor: 'Dell Technologies', vendorEmail: 'invoices@dell.com', vendorPhone: '+1-555-0102', vendorAddress: '1 Dell Way, Round Rock, TX 78682', vendorTaxId: 'US-TAX-12034', category: 'Hardware', issueDate: '2024-11-15', dueDate: '2024-12-15', amount: 8750.00, status: 'Approved', paymentTerms: 'Net 30', poNumber: 'PO-8801', notes: 'Bulk laptop order for Q1 onboarding.', approvedBy: 'Admin User', approvedAt: '2024-11-20',
    lineItems: [
      { id: '2a', description: 'Latitude 5540 Laptop', quantity: 5, unitPrice: 1450.00, taxPercent: 8 },
      { id: '2b', description: 'Docking Station WD19S', quantity: 5, unitPrice: 250.00, taxPercent: 8 },
    ],
  },
  {
    id: '3', invoiceNumber: 'INV-2024-003', vendor: 'AWS', vendorEmail: 'aws-billing@amazon.com', vendorPhone: '+1-555-0103', vendorAddress: '410 Terry Ave N, Seattle, WA 98109', vendorTaxId: 'US-TAX-44821', category: 'Cloud Services', issueDate: '2024-12-01', dueDate: '2025-01-01', amount: 12340.50, status: 'Pending', paymentTerms: 'Net 30', poNumber: 'PO-8845', notes: 'December cloud usage charges.',
    lineItems: [
      { id: '3a', description: 'EC2 Compute Hours', quantity: 1, unitPrice: 6200.00, taxPercent: 0 },
      { id: '3b', description: 'S3 Storage', quantity: 1, unitPrice: 3400.50, taxPercent: 0 },
      { id: '3c', description: 'RDS Database', quantity: 1, unitPrice: 2740.00, taxPercent: 0 },
    ],
  },
  {
    id: '4', invoiceNumber: 'INV-2024-004', vendor: 'Adobe Systems', vendorEmail: 'billing@adobe.com', vendorPhone: '+1-555-0104', vendorAddress: '345 Park Ave, San Jose, CA 95110', vendorTaxId: 'US-TAX-77123', category: 'Software Subscriptions', issueDate: '2024-11-01', dueDate: '2024-11-30', amount: 1599.99, status: 'Approved', paymentTerms: 'Net 30', poNumber: 'PO-8790', notes: 'Creative Cloud team licenses.', approvedBy: 'Admin User', approvedAt: '2024-11-10',
    lineItems: [
      { id: '4a', description: 'Creative Cloud All Apps - Team', quantity: 3, unitPrice: 533.33, taxPercent: 10 },
    ],
  },
  {
    id: '5', invoiceNumber: 'INV-2024-005', vendor: 'FedEx', vendorEmail: 'billing@fedex.com', vendorPhone: '+1-555-0105', vendorAddress: '942 S Shady Grove Rd, Memphis, TN 38120', vendorTaxId: 'US-TAX-55901', category: 'Logistics', issueDate: '2024-12-05', dueDate: '2025-01-05', amount: 387.50, status: 'Pending', paymentTerms: 'Net 30', poNumber: 'PO-8851', notes: 'Monthly shipping charges.',
    lineItems: [
      { id: '5a', description: 'Express Shipping - Domestic', quantity: 12, unitPrice: 24.50, taxPercent: 5 },
      { id: '5b', description: 'International Priority', quantity: 2, unitPrice: 47.75, taxPercent: 5 },
    ],
  },
  {
    id: '6', invoiceNumber: 'INV-2024-006', vendor: 'Office Depot', vendorEmail: 'orders@officedepot.com', vendorPhone: '+1-555-0106', vendorAddress: '6600 N Military Trail, Boca Raton, FL 33496', vendorTaxId: 'US-TAX-33401', category: 'Office Supplies', issueDate: '2024-11-20', dueDate: '2024-12-20', amount: 249.99, status: 'Rejected', paymentTerms: 'Net 30', poNumber: 'PO-8812', notes: 'Duplicate order — already fulfilled.', rejectedBy: 'Admin User', rejectedAt: '2024-11-22', rejectionReason: 'Duplicate invoice — original already processed as INV-2024-003.',
    lineItems: [
      { id: '6a', description: 'A4 Paper Case (5000 sheets)', quantity: 5, unitPrice: 34.99, taxPercent: 7 },
      { id: '6b', description: 'Ink Cartridge Set', quantity: 2, unitPrice: 37.50, taxPercent: 7 },
    ],
  },
  {
    id: '7', invoiceNumber: 'INV-2024-007', vendor: 'Zoom Communications', vendorEmail: 'billing@zoom.us', vendorPhone: '+1-555-0107', vendorAddress: '55 Almaden Blvd, San Jose, CA 95113', vendorTaxId: 'US-TAX-91023', category: 'Software Subscriptions', issueDate: '2024-12-01', dueDate: '2025-01-01', amount: 499.90, status: 'Approved', paymentTerms: 'Net 30', poNumber: 'PO-8847', notes: 'Monthly business plan.', approvedBy: 'Admin User', approvedAt: '2024-12-02',
    lineItems: [
      { id: '7a', description: 'Zoom Business - 10 licenses', quantity: 10, unitPrice: 49.99, taxPercent: 0 },
    ],
  },
  {
    id: '8', invoiceNumber: 'INV-2024-008', vendor: 'Salesforce', vendorEmail: 'billing@salesforce.com', vendorPhone: '+1-555-0108', vendorAddress: '415 Mission St, San Francisco, CA 94105', vendorTaxId: 'US-TAX-60112', category: 'Software Subscriptions', issueDate: '2024-10-15', dueDate: '2024-11-15', amount: 24750.00, status: 'Approved', paymentTerms: 'Net 30', poNumber: 'PO-8775', notes: 'Enterprise CRM annual contract.', approvedBy: 'Admin User', approvedAt: '2024-10-20',
    lineItems: [
      { id: '8a', description: 'Sales Cloud Enterprise - Annual', quantity: 15, unitPrice: 1500.00, taxPercent: 10 },
      { id: '8b', description: 'Service Cloud Add-on', quantity: 15, unitPrice: 150.00, taxPercent: 10 },
    ],
  },
  {
    id: '9', invoiceNumber: 'INV-2024-009', vendor: 'Cloudflare', vendorEmail: 'billing@cloudflare.com', vendorPhone: '+1-555-0109', vendorAddress: '101 Townsend St, San Francisco, CA 94107', vendorTaxId: 'US-TAX-78445', category: 'Cloud Services', issueDate: '2024-12-01', dueDate: '2025-01-01', amount: 200.00, status: 'Pending', paymentTerms: 'Net 30', poNumber: 'PO-8849', notes: 'Pro plan + Workers usage.',
    lineItems: [
      { id: '9a', description: 'Pro Plan', quantity: 1, unitPrice: 25.00, taxPercent: 0 },
      { id: '9b', description: 'Workers Paid - 10M requests', quantity: 1, unitPrice: 175.00, taxPercent: 0 },
    ],
  },
  {
    id: '10', invoiceNumber: 'INV-2024-010', vendor: 'Slack Technologies', vendorEmail: 'billing@slack.com', vendorPhone: '+1-555-0110', vendorAddress: '500 Howard St, San Francisco, CA 94105', vendorTaxId: 'US-TAX-23456', category: 'Software Subscriptions', issueDate: '2024-11-01', dueDate: '2024-12-01', amount: 1250.00, status: 'Approved', paymentTerms: 'Net 30', poNumber: 'PO-8798', notes: 'Business+ plan.', approvedBy: 'Admin User', approvedAt: '2024-11-05',
    lineItems: [
      { id: '10a', description: 'Slack Business+ - 50 users', quantity: 50, unitPrice: 25.00, taxPercent: 0 },
    ],
  },
  {
    id: '11', invoiceNumber: 'INV-2024-011', vendor: 'WeWork', vendorEmail: 'billing@wework.com', vendorPhone: '+1-555-0111', vendorAddress: '75 Rockefeller Plz, New York, NY 10019', vendorTaxId: 'US-TAX-44567', category: 'Professional Services', issueDate: '2024-12-01', dueDate: '2025-01-01', amount: 4500.00, status: 'Pending', paymentTerms: 'Net 15', poNumber: 'PO-8852', notes: 'December coworking space rental.',
    lineItems: [
      { id: '11a', description: 'Hot Desk - 10 seats', quantity: 10, unitPrice: 350.00, taxPercent: 8 },
      { id: '11b', description: 'Meeting Room Credits', quantity: 20, unitPrice: 50.00, taxPercent: 8 },
    ],
  },
  {
    id: '12', invoiceNumber: 'INV-2024-012', vendor: 'HubSpot', vendorEmail: 'billing@hubspot.com', vendorPhone: '+1-555-0112', vendorAddress: '25 1st St, Cambridge, MA 02141', vendorTaxId: 'US-TAX-89012', category: 'Marketing', issueDate: '2024-11-15', dueDate: '2024-12-15', amount: 3200.00, status: 'Rejected', paymentTerms: 'Net 30', poNumber: 'PO-8810', notes: 'Marketing Hub upgrade not approved.', rejectedBy: 'Admin User', rejectedAt: '2024-11-18', rejectionReason: 'Budget not approved for this quarter.',
    lineItems: [
      { id: '12a', description: 'Marketing Hub Professional', quantity: 1, unitPrice: 3200.00, taxPercent: 0 },
    ],
  },
  {
    id: '13', invoiceNumber: 'INV-2024-013', vendor: 'United Airlines', vendorEmail: 'receipts@united.com', vendorPhone: '+1-555-0113', vendorAddress: '233 S Wacker Dr, Chicago, IL 60606', vendorTaxId: 'US-TAX-55678', category: 'Travel', issueDate: '2024-12-03', dueDate: '2025-01-03', amount: 1875.00, status: 'Pending', paymentTerms: 'Net 30', poNumber: 'PO-8855', notes: 'Team offsite travel expenses.',
    lineItems: [
      { id: '13a', description: 'Round-trip SFO-JFK Economy', quantity: 3, unitPrice: 625.00, taxPercent: 0 },
    ],
  },
  {
    id: '14', invoiceNumber: 'INV-2024-014', vendor: 'Figma', vendorEmail: 'billing@figma.com', vendorPhone: '+1-555-0114', vendorAddress: '760 Market St, San Francisco, CA 94102', vendorTaxId: 'US-TAX-67890', category: 'Software Subscriptions', issueDate: '2024-12-01', dueDate: '2025-01-01', amount: 540.00, status: 'Approved', paymentTerms: 'Net 30', poNumber: 'PO-8848', notes: 'Organization plan for design team.', approvedBy: 'Admin User', approvedAt: '2024-12-01',
    lineItems: [
      { id: '14a', description: 'Figma Organization - 3 editors', quantity: 3, unitPrice: 180.00, taxPercent: 0 },
    ],
  },
  {
    id: '15', invoiceNumber: 'INV-2024-015', vendor: 'Datadog', vendorEmail: 'billing@datadog.com', vendorPhone: '+1-555-0115', vendorAddress: '620 8th Ave, New York, NY 10018', vendorTaxId: 'US-TAX-12345', category: 'Cloud Services', issueDate: '2024-12-01', dueDate: '2025-01-01', amount: 1890.00, status: 'Pending', paymentTerms: 'Net 30', poNumber: 'PO-8853', notes: 'Infrastructure monitoring.',
    lineItems: [
      { id: '15a', description: 'Infrastructure Pro - 20 hosts', quantity: 20, unitPrice: 69.00, taxPercent: 0 },
      { id: '15b', description: 'Log Management - 10GB/day', quantity: 1, unitPrice: 510.00, taxPercent: 0 },
    ],
  },
];
