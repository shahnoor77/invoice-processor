"""Google Sheets integration — saves invoice scan history."""
import json
import os
import time
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_NAME = "Invoice History"

# Simple TTL cache — avoids hitting Google Sheets API on every page load
_cache = {"data": None, "ts": 0}
CACHE_TTL = 30  # seconds


def _invalidate_cache():
    _cache["data"] = None
    _cache["ts"] = 0

HEADERS = [
    "User Email",
    "Timestamp",
    "File Name",
    "Approval Status",
    "Invoice Number",
    "Invoice Date",
    "Due Date",
    "Payment Terms",
    "Purchase Order",
    "Sender Name",
    "Sender Address",
    "Sender City",
    "Sender Country",
    "Sender Phone",
    "Sender Email",
    "Sender Tax ID",
    "Receiver Name",
    "Receiver Address",
    "Receiver City",
    "Receiver Country",
    "Receiver Phone",
    "Receiver Email",
    "Receiver Tax ID",
    "Currency",
    "Subtotal",
    "Discount",
    "Tax Rate (%)",
    "Tax Amount",
    "Shipping",
    "Total Amount",
    "Amount Paid",
    "Amount Due",
    "Notes",
    "Bank Details",
    "OCR Confidence",
    "Full JSON",
]


def _get_client() -> gspread.Client:
    creds_file = os.environ.get("GOOGLE_CREDENTIALS_FILE", "google_credentials.json")
    if not os.path.isabs(creds_file):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        creds_file = os.path.join(project_root, creds_file)
    creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    return gspread.authorize(creds)


def _ensure_sheet(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    existing = [ws.title for ws in spreadsheet.worksheets()]
    if SHEET_NAME not in existing:
        ws = spreadsheet.add_worksheet(title=SHEET_NAME, rows=1000, cols=len(HEADERS))
        ws.append_row(HEADERS, value_input_option="RAW")
        ws.format("A1:AJ1", {"textFormat": {"bold": True}})
    else:
        ws = spreadsheet.worksheet(SHEET_NAME)
        # Check if headers match — update if User Email column is missing
        current_headers = ws.row_values(1)
        if current_headers and current_headers[0] != "User Email":
            # Prepend User Email column to existing headers
            ws.insert_cols([['']], col=1)
            ws.update_cell(1, 1, "User Email")
    return spreadsheet.worksheet(SHEET_NAME)


def _val(d: dict, *keys, default=""):
    """Safely get nested dict value."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k)
        if d is None:
            return default
    return d if d is not None else default


def save_invoice(invoice_data: dict, file_name: str, approval_status: str, user_email: str = ""):
    """Append one row per invoice to the Invoice History sheet."""
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        return False, "GOOGLE_SHEET_ID not set in .env"
    try:
        gc = _get_client()
        sp = gc.open_by_key(sheet_id)
        ws = _ensure_sheet(sp)

        s = invoice_data.get("sender") or {}
        r = invoice_data.get("receiver") or {}

        row = [
            user_email,                                           # User Email
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),        # Timestamp
            file_name,                                            # File Name
            approval_status,                                      # Approval Status
            _val(invoice_data, "invoice_number"),             # Invoice Number
            _val(invoice_data, "invoice_date"),               # Invoice Date
            _val(invoice_data, "due_date"),                   # Due Date
            _val(invoice_data, "payment_terms"),              # Payment Terms
            _val(invoice_data, "purchase_order"),             # Purchase Order
            _val(s, "name"),                                  # Sender Name
            _val(s, "address"),                               # Sender Address
            _val(s, "city"),                                  # Sender City
            _val(s, "country"),                               # Sender Country
            _val(s, "phone"),                                 # Sender Phone
            _val(s, "email"),                                 # Sender Email
            _val(s, "tax_id"),                                # Sender Tax ID
            _val(r, "name"),                                  # Receiver Name
            _val(r, "address"),                               # Receiver Address
            _val(r, "city"),                                  # Receiver City
            _val(r, "country"),                               # Receiver Country
            _val(r, "phone"),                                 # Receiver Phone
            _val(r, "email"),                                 # Receiver Email
            _val(r, "tax_id"),                                # Receiver Tax ID
            _val(invoice_data, "currency"),                   # Currency
            _val(invoice_data, "subtotal"),                   # Subtotal
            _val(invoice_data, "discount_total"),             # Discount
            _val(invoice_data, "tax_rate"),                   # Tax Rate
            _val(invoice_data, "tax_amount"),                 # Tax Amount
            _val(invoice_data, "shipping"),                   # Shipping
            _val(invoice_data, "total_amount"),               # Total Amount
            _val(invoice_data, "amount_paid"),                # Amount Paid
            _val(invoice_data, "amount_due"),                 # Amount Due
            _val(invoice_data, "notes"),                      # Notes
            _val(invoice_data, "bank_details"),               # Bank Details
            _val(invoice_data, "confidence"),                 # OCR Confidence
            json.dumps(invoice_data, ensure_ascii=False),     # Full JSON
        ]

        ws.append_row(row, value_input_option="USER_ENTERED")
        _invalidate_cache()
        return True, None
    except Exception as e:
        return False, str(e)


def get_processed_invoices(user_email: str = "") -> list:
    """Return invoices filtered by user_email. Uses 30s cache to avoid slow Sheet reads."""
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        return []
    try:
        # Use cache if fresh
        if _cache["data"] is not None and (time.time() - _cache["ts"]) < CACHE_TTL:
            all_rows = _cache["data"]
        else:
            gc = _get_client()
            sp = gc.open_by_key(sheet_id)
            ws = _ensure_sheet(sp)
            all_values = ws.get_all_values()
            if len(all_values) < 2:
                return []
            headers = [h for h in all_values[0] if h.strip()]
            all_rows = []
            for idx, row in enumerate(all_values[1:]):
                row = list(row[:len(headers)])
                while len(row) < len(headers):
                    row.append('')
                d = dict(zip(headers, row))
                d["_sheet_row"] = idx + 2  # 1-based, +1 for header
                all_rows.append(d)
            _cache["data"] = all_rows
            _cache["ts"] = time.time()

        if user_email:
            return [r for r in all_rows if r.get("User Email", "") == user_email]
        return all_rows
    except Exception as e:
        print(f"Sheets read error: {e}")
        return []


def update_approval_status(row_number: int, status: str):
    """Update the Approval Status cell for a specific row."""
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        return False, "GOOGLE_SHEET_ID not set"
    try:
        gc = _get_client()
        sp = gc.open_by_key(sheet_id)
        ws = _ensure_sheet(sp)
        # Find the Approval Status column index
        headers = ws.row_values(1)
        col_idx = headers.index("Approval Status") + 1  # 1-based
        ws.update_cell(row_number, col_idx, status)
        _invalidate_cache()
        return True, None
    except Exception as e:
        return False, str(e)


def log_processing(file_name: str, status: str, error: str = "", model: str = ""):
    pass  # kept for compatibility
