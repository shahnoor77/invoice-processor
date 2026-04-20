"""
Invoice Processing Worker — picks up queued jobs and runs the AI crew.
Threading model:
- One ThreadPoolExecutor for OCR (CPU-bound, parallelizable)
- One job processed per user at a time (LLM rate limits)
- Destination routing runs in parallel threads on approval
"""
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Thread, Lock
from typing import Optional, Any
from pydantic import BaseModel, field_validator, model_validator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from dotenv import load_dotenv
load_dotenv(override=True)

from database import SessionLocal
from models import Invoice, InvoiceLineItem, ProcessingJob

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("worker")
# Suppress noisy litellm/httpx debug lines unless explicitly enabled
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

_running = False
_user_locks: dict[str, Lock] = {}  # one lock per user — prevents parallel AI calls per user
_user_locks_lock = Lock()           # protects the dict itself

# OCR thread pool — parallel file reading
_ocr_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ocr")


def _parse_json(text: str):
    if not text:
        return None

    def try_parse(s: str):
        s = s.strip()
        # Fix invalid JSON numbers: 00.00 → 0.00, 00 → 0 (JSON doesn't allow leading zeros)
        s = re.sub(r'\b0{2,}(\.\d+)', r'0\1', s)   # 00.00 → 0.00
        s = re.sub(r':\s*0{2,}([^.])', r': 0\1', s) # : 00, → : 0,
        try:
            return json.loads(s)
        except Exception:
            return None

    # 1. Direct parse
    result = try_parse(text)
    if result:
        return result

    # 2. Strip <think>...</think> blocks (qwen3 reasoning)
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    if cleaned != text:
        result = try_parse(cleaned)
        if result:
            return result
        text = cleaned  # use cleaned for further attempts

    # 3. Extract from fenced code block
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.DOTALL)
    if m:
        result = try_parse(m.group(1))
        if result:
            return result

    # 4. Find the JSON object in the text
    start = text.find('{')
    if start == -1:
        return None
    fragment = text[start:]

    # 5. Try the full fragment
    result = try_parse(fragment)
    if result:
        return result

    # 6. Truncated JSON repair — walk char by char tracking depth
    # Build the longest valid JSON by closing open structures
    depth = 0
    in_string = False
    escape_next = False
    last_complete_pos = -1

    for i, ch in enumerate(fragment):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{' or ch == '[':
            depth += 1
        elif ch == '}' or ch == ']':
            depth -= 1
            if depth == 0:
                last_complete_pos = i

    if last_complete_pos > 0:
        result = try_parse(fragment[:last_complete_pos + 1])
        if result:
            return result

    # 7. Truncated — try to close open braces/brackets
    if depth > 0:
        # Strip trailing incomplete tokens (partial strings, trailing commas)
        repaired = re.sub(r',\s*$', '', fragment.rstrip())
        # Close any open string
        if in_string:
            repaired += '"'
        # Close open structures
        close_stack = []
        d2 = 0
        in_s2 = False
        esc2 = False
        for ch in repaired:
            if esc2:
                esc2 = False
                continue
            if ch == '\\' and in_s2:
                esc2 = True
                continue
            if ch == '"':
                in_s2 = not in_s2
                continue
            if in_s2:
                continue
            if ch == '{':
                close_stack.append('}')
            elif ch == '[':
                close_stack.append(']')
            elif ch in ('}', ']'):
                if close_stack:
                    close_stack.pop()

        repaired += ''.join(reversed(close_stack))
        result = try_parse(repaired)
        if result:
            log.info("[Parse] Recovered truncated JSON via brace repair")
            return result

    return None


# ── Pydantic coercion models ──────────────────────────────────────────────────
# Used to normalize raw LLM output before validation/DB save.
# All fields are Optional — we never reject partial data.
# Validators coerce common LLM quirks: "25,000.00" → 25000.0, "N/A" → None, etc.

_NULL_STRINGS = {"null", "none", "n/a", "na", "nil", "-", "", "undefined"}

def _coerce_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in _NULL_STRINGS else s

def _coerce_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace(" ", "").strip())
    except Exception:
        return None

def _coerce_date(v: Any) -> Optional[str]:
    """Try to normalize dates to YYYY-MM-DD. Returns as-is if can't parse."""
    if v is None:
        return None
    s = str(v).strip()
    if s.lower() in _NULL_STRINGS:
        return None
    # Already correct format
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    # Try common formats
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%d/%m/%Y", "%m/%d/%Y",
                "%d-%m-%Y", "%m-%d-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            from datetime import datetime as dt
            return dt.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return s  # return as-is rather than lose the value


class _BankModel(BaseModel):
    model_config = {"extra": "ignore"}
    bank_name: Optional[str] = None
    account_holder: Optional[str] = None
    account_number: Optional[str] = None
    iban: Optional[str] = None
    swift_bic: Optional[str] = None
    routing_number: Optional[str] = None
    sort_code: Optional[str] = None
    branch: Optional[str] = None
    bank_address: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def coerce_strings(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return {}
        return {k: _coerce_str(v) for k, v in data.items()}


class _PartyModel(BaseModel):
    model_config = {"extra": "ignore"}
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    tax_id: Optional[str] = None
    vat_number: Optional[str] = None
    registration_number: Optional[str] = None
    bank: Optional[_BankModel] = None

    @model_validator(mode="before")
    @classmethod
    def coerce_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return {}
        result = {}
        for k, v in data.items():
            if k == "bank":
                result[k] = v if isinstance(v, dict) else {}
            else:
                result[k] = _coerce_str(v)
        return result


class _LineItemModel(BaseModel):
    model_config = {"extra": "ignore"}
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    discount_percent: Optional[float] = None
    discount_amount: Optional[float] = None
    tax_percent: Optional[float] = None
    tax_amount: Optional[float] = None
    total: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def coerce_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return {}
        result = {}
        for k, v in data.items():
            if k in ("description", "unit"):
                result[k] = _coerce_str(v)
            else:
                result[k] = _coerce_float(v)
        return result


class InvoiceExtraction(BaseModel):
    """Pydantic model for LLM-extracted invoice data. Coerces, never raises."""
    model_config = {"extra": "ignore"}

    sender: Optional[_PartyModel] = None
    receiver: Optional[_PartyModel] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    delivery_date: Optional[str] = None
    purchase_order: Optional[str] = None
    payment_terms: Optional[str] = None
    payment_method: Optional[str] = None
    reference: Optional[str] = None
    line_items: Optional[list[_LineItemModel]] = None
    subtotal: Optional[float] = None
    discount_total: Optional[float] = None
    discount_percent: Optional[float] = None
    tax_rate: Optional[float] = None
    tax_amount: Optional[float] = None
    tax_type: Optional[str] = None
    shipping: Optional[float] = None
    handling: Optional[float] = None
    other_charges: Optional[float] = None
    total_amount: Optional[float] = None
    amount_paid: Optional[float] = None
    amount_due: Optional[float] = None
    deposit: Optional[float] = None
    currency: Optional[str] = None
    exchange_rate: Optional[float] = None
    notes: Optional[str] = None
    terms_and_conditions: Optional[str] = None
    confidence: Optional[str] = "HIGH"

    @field_validator("invoice_date", "due_date", "delivery_date", mode="before")
    @classmethod
    def coerce_date(cls, v: Any) -> Any:
        return _coerce_date(v)

    @field_validator("invoice_number", "purchase_order", "reference",
                     "payment_terms", "payment_method", "tax_type",
                     "currency", "notes", "terms_and_conditions", "confidence", mode="before")
    @classmethod
    def coerce_str(cls, v: Any) -> Any:
        return _coerce_str(v)

    @field_validator("subtotal", "discount_total", "discount_percent", "tax_rate",
                     "tax_amount", "shipping", "handling", "other_charges",
                     "total_amount", "amount_paid", "amount_due", "deposit",
                     "exchange_rate", mode="before")
    @classmethod
    def coerce_num(cls, v: Any) -> Any:
        return _coerce_float(v)

    @model_validator(mode="before")
    @classmethod
    def reject_refusal(cls, data: Any) -> Any:
        """Reject dicts that look like model refusals rather than invoice data."""
        if not isinstance(data, dict):
            raise ValueError("Not a dict")
        real_keys = {"invoice_number", "sender", "receiver", "line_items",
                     "total_amount", "subtotal", "amount_due"}
        if not real_keys.intersection(data.keys()):
            raise ValueError(f"Looks like a refusal response, not invoice data: {list(data.keys())}")
        return data

    def to_dict(self) -> dict:
        """Convert back to plain dict for downstream processing."""
        d = self.model_dump(exclude_none=False)
        # Convert nested models back to dicts
        if self.sender:
            d["sender"] = self.sender.model_dump(exclude_none=False)
            if self.sender.bank:
                d["sender"]["bank"] = self.sender.bank.model_dump(exclude_none=False)
        if self.receiver:
            d["receiver"] = self.receiver.model_dump(exclude_none=False)
            if self.receiver.bank:
                d["receiver"]["bank"] = self.receiver.bank.model_dump(exclude_none=False)
        if self.line_items:
            d["line_items"] = [li.model_dump(exclude_none=False) for li in self.line_items]
        return d


def _coerce_extracted(raw: dict) -> dict:
    """
    Run raw LLM output through Pydantic coercion.
    Returns the coerced dict, or the original if validation fails entirely.
    """
    try:
        parsed = InvoiceExtraction.model_validate(raw)
        coerced = parsed.to_dict()
        log.info(f"[Coerce] Pydantic coercion OK — invoice_number={coerced.get('invoice_number')!r}")
        return coerced
    except Exception as e:
        log.warning(f"[Coerce] Pydantic coercion failed ({e}) — using raw dict")
        return raw


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None


def _validate_and_correct(extracted: dict) -> dict:
    """
    Validate invoice calculations and auto-correct where possible.
    Also strips misclassified summary rows (discount/tax/total) from line_items.
    """
    TOLERANCE = 0.02
    issues = []

    def sf(v):
        return _safe_float(v)

    # ── 0. Strip misclassified summary rows from line_items ───────────────────
    # Only strip a row if its description is PURELY a summary label AND it has no qty/price.
    # Use word-boundary matching to avoid false positives like "delivery service" or "total hours".
    import re as _re

    # These must match the WHOLE description (or be the dominant word) — not substrings of real items
    SUMMARY_EXACT = {
        "discount", "rebate", "promo", "promotion", "coupon", "early payment discount",
        "tax", "vat", "gst", "hst", "pst", "sales tax", "withholding tax", "income tax",
        "shipping", "freight", "delivery", "postage", "shipping & handling",
        "handling", "packaging",
        "subtotal", "sub total", "sub-total",
        "total", "grand total", "invoice total",
        "amount due", "balance due", "balance",
        "amount paid", "payment received", "deposit",
        "rounding", "rounding adjustment", "adjustment",
    }

    def _is_summary_row(desc: str, qty, price) -> bool:
        """
        A row is a summary row ONLY if:
        1. Its description exactly matches (or starts with) a known summary keyword, AND
        2. It has no quantity AND no unit_price (pure adjustment row)
        """
        if qty is not None or price is not None:
            # Has qty or price → it's a real product/service line, never strip it
            return False
        d = desc.strip().lower()
        # Exact match
        if d in SUMMARY_EXACT:
            return True
        # Starts with a summary keyword followed by space/colon/percent/number
        for kw in SUMMARY_EXACT:
            if _re.match(rf'^{_re.escape(kw)}[\s:(%\-]', d):
                return True
        return False

    raw_items = extracted.get("line_items") or []
    clean_items = []
    rescued = {"discount_total": 0.0, "tax_amount": 0.0, "shipping": 0.0, "handling": 0.0}

    for item in raw_items:
        desc = (item.get("description") or "").lower().strip()
        qty = sf(item.get("quantity"))
        price = sf(item.get("unit_price"))
        total = sf(item.get("total"))

        if _is_summary_row(desc, qty, price):
            # Rescue the value into the correct top-level field
            if any(kw in desc for kw in ("discount", "rebate", "promo", "coupon")):
                val = total or sf(item.get("discount_amount")) or 0.0
                if val and val > 0:
                    rescued["discount_total"] += abs(val)
                    log.info(f"[Validate] Rescued discount row '{item.get('description')}' → discount_total += {abs(val)}")
            elif any(kw in desc for kw in ("tax", "vat", "gst", "hst", "pst", "withholding")):
                val = total or sf(item.get("tax_amount")) or 0.0
                if val and val > 0:
                    rescued["tax_amount"] += abs(val)
                    log.info(f"[Validate] Rescued tax row '{item.get('description')}' → tax_amount += {abs(val)}")
            elif any(kw in desc for kw in ("shipping", "freight", "postage")):
                val = total or 0.0
                if val and val > 0:
                    rescued["shipping"] += abs(val)
                    log.info(f"[Validate] Rescued shipping row '{item.get('description')}' → shipping += {abs(val)}")
            elif any(kw in desc for kw in ("handling", "packaging")):
                val = total or 0.0
                if val and val > 0:
                    rescued["handling"] += abs(val)
                    log.info(f"[Validate] Rescued handling row '{item.get('description')}' → handling += {abs(val)}")
            else:
                log.info(f"[Validate] Removed summary row from line_items: '{item.get('description')}'")
        else:
            clean_items.append(item)

    extracted["line_items"] = clean_items

    # Apply rescued values to top-level fields (only if not already set)
    if rescued["discount_total"] > 0 and not sf(extracted.get("discount_total")):
        extracted["discount_total"] = round(rescued["discount_total"], 2)
    if rescued["tax_amount"] > 0 and not sf(extracted.get("tax_amount")):
        extracted["tax_amount"] = round(rescued["tax_amount"], 2)
    if rescued["shipping"] > 0 and not sf(extracted.get("shipping")):
        extracted["shipping"] = round(rescued["shipping"], 2)
    if rescued["handling"] > 0 and not sf(extracted.get("handling")):
        extracted["handling"] = round(rescued["handling"], 2)

    # ── 1. Recompute line item totals ─────────────────────────────────────────
    for idx, item in enumerate(clean_items):
        qty = sf(item.get("quantity"))
        price = sf(item.get("unit_price"))
        discount_pct = sf(item.get("discount_percent"))
        discount_amt = sf(item.get("discount_amount"))
        tax_pct = sf(item.get("tax_percent"))
        tax_amt = sf(item.get("tax_amount"))
        stated_total = sf(item.get("total"))

        if qty is not None and price is not None:
            base = qty * price
            if discount_amt is not None:
                base -= discount_amt
            elif discount_pct is not None:
                base -= base * discount_pct / 100
            if tax_amt is not None:
                computed = base + tax_amt
            elif tax_pct is not None:
                computed = base + base * tax_pct / 100
            else:
                computed = base

            if stated_total is not None and abs(computed - stated_total) > TOLERANCE:
                issues.append({
                    "field": f"line_items[{idx}].total",
                    "original": stated_total,
                    "corrected": round(computed, 2),
                    "note": f"Line {idx+1}: {qty} × {price} = {round(computed,2)}, invoice shows {stated_total}",
                })
                item["total"] = round(computed, 2)
            elif stated_total is None:
                item["total"] = round(computed, 2)

    # ── 2. Recompute subtotal from line items ─────────────────────────────────
    computed_subtotal = None
    if clean_items:
        totals = [sf(item.get("total")) for item in clean_items]
        if all(t is not None for t in totals):
            computed_subtotal = round(sum(totals), 2)  # type: ignore[arg-type]

    stated_subtotal = sf(extracted.get("subtotal"))
    if computed_subtotal is not None:
        if stated_subtotal is not None and abs(computed_subtotal - stated_subtotal) > TOLERANCE:
            issues.append({
                "field": "subtotal",
                "original": stated_subtotal,
                "corrected": computed_subtotal,
                "note": f"Sum of line items = {computed_subtotal}, invoice shows {stated_subtotal}",
            })
            extracted["subtotal"] = computed_subtotal
        elif stated_subtotal is None:
            extracted["subtotal"] = computed_subtotal

    effective_subtotal = sf(extracted.get("subtotal")) or 0.0

    # ── 3. Validate / derive tax amount ──────────────────────────────────────
    tax_rate = sf(extracted.get("tax_rate"))
    stated_tax = sf(extracted.get("tax_amount"))
    computed_tax = None
    if tax_rate is not None and effective_subtotal:
        computed_tax = round(effective_subtotal * tax_rate / 100, 2)
        if stated_tax is not None and abs(computed_tax - stated_tax) > TOLERANCE:
            issues.append({
                "field": "tax_amount",
                "original": stated_tax,
                "corrected": computed_tax,
                "note": f"{effective_subtotal} × {tax_rate}% = {computed_tax}, invoice shows {stated_tax}",
            })
            extracted["tax_amount"] = computed_tax
        elif stated_tax is None:
            extracted["tax_amount"] = computed_tax

    effective_tax = sf(extracted.get("tax_amount")) or 0.0

    # ── 4. Validate total_amount ──────────────────────────────────────────────
    discount_total = sf(extracted.get("discount_total")) or 0.0
    shipping = sf(extracted.get("shipping")) or 0.0
    handling = sf(extracted.get("handling")) or 0.0
    other = sf(extracted.get("other_charges")) or 0.0

    computed_total = round(
        effective_subtotal - discount_total + effective_tax + shipping + handling + other, 2
    )
    stated_total_amt = sf(extracted.get("total_amount"))

    if stated_total_amt is not None and abs(computed_total - stated_total_amt) > TOLERANCE:
        issues.append({
            "field": "total_amount",
            "original": stated_total_amt,
            "corrected": computed_total,
            "note": (
                f"subtotal({effective_subtotal}) - discount({discount_total}) "
                f"+ tax({effective_tax}) + shipping({shipping}) + other({other}) "
                f"= {computed_total}, invoice shows {stated_total_amt}"
            ),
        })
        extracted["total_amount"] = computed_total
    elif stated_total_amt is None and effective_subtotal:
        extracted["total_amount"] = computed_total

    # ── 5. Validate amount_due ────────────────────────────────────────────────
    effective_total = sf(extracted.get("total_amount")) or 0.0
    amount_paid = sf(extracted.get("amount_paid")) or 0.0
    stated_due = sf(extracted.get("amount_due"))
    computed_due = round(effective_total - amount_paid, 2)

    if stated_due is not None and abs(computed_due - stated_due) > TOLERANCE:
        issues.append({
            "field": "amount_due",
            "original": stated_due,
            "corrected": computed_due,
            "note": f"total({effective_total}) - paid({amount_paid}) = {computed_due}, invoice shows {stated_due}",
        })
        extracted["amount_due"] = computed_due
    elif stated_due is None and effective_total:
        extracted["amount_due"] = computed_due

    extracted["validation_issues"] = issues
    if issues:
        log.info(f"[Validate] {len(issues)} correction(s): {[i['field'] for i in issues]}")
    return extracted


def _get_user_lock(user_id: str) -> Lock:
    """Get or create a per-user lock to prevent parallel AI calls for same user."""
    with _user_locks_lock:
        if user_id not in _user_locks:
            _user_locks[user_id] = Lock()
        return _user_locks[user_id]


def _redownload_attachment(job, db) -> bool:
    """Re-download attachment from email if temp file was lost."""
    try:
        from models import EmailConfig
        cfg = db.query(EmailConfig).filter(EmailConfig.user_id == job.user_id).first()
        if not cfg:
            return False

        import imaplib, email as email_lib, tempfile
        if cfg.imap_encryption in ("SSL/TLS", "SSL"):
            mail = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port)
        else:
            mail = imaplib.IMAP4(cfg.imap_host, cfg.imap_port)

        from password_encryption import decrypt_password
        mail.login(cfg.username, decrypt_password(cfg.password))
        mail.select(cfg.folder or "INBOX")

        # Search by message ID
        _, msg_ids = mail.search(None, f'HEADER Message-ID "{job.email_message_id}"')
        ids = msg_ids[0].split()
        if not ids:
            # Fall back to searching by subject
            if job.email_subject:
                _, msg_ids = mail.search(None, f'SUBJECT "{job.email_subject}"')
                ids = msg_ids[0].split()

        if not ids:
            mail.logout()
            return False

        _, msg_data = mail.fetch(ids[0], "(RFC822)")
        msg = email_lib.message_from_bytes(msg_data[0][1])

        for part in msg.walk():
            filename = part.get_filename()
            if not filename:
                continue
            from email.header import decode_header
            parts = decode_header(filename)
            filename = "".join(p.decode(e or "utf-8") if isinstance(p, bytes) else p for p, e in parts)
            safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")

            if safe_name == job.file_name:
                payload = part.get_payload(decode=True)
                if payload:
                    tmp_dir = tempfile.mkdtemp(prefix="email_invoice_recovered_")
                    new_path = os.path.join(tmp_dir, safe_name)
                    with open(new_path, "wb") as f:
                        f.write(payload)
                    job.file_path = new_path
                    db.commit()
                    log.info(f"Job {job.id}: re-downloaded attachment to {new_path}")
                    mail.logout()
                    return True

        mail.logout()
        return False
    except Exception as e:
        log.error(f"Re-download failed for job {job.id}: {e}")
        return False


def _extract_ocr_async(file_path: str) -> str:
    """Run OCR in thread pool — non-blocking."""
    future = _ocr_executor.submit(_extract_ocr, file_path)
    return future.result(timeout=120)  # 2 min timeout for OCR


def _extract_ocr(file_path: str) -> str:
    """Extract text from PDF or image file."""
    from invoice_processing_automation_system.tools.custom_tool import (
        PDFTextExtractor, ImageTextExtractor, extract_image_with_llava
    )
    ext = os.path.splitext(file_path)[-1].lower()
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://110.39.187.178:11434")

    log.info(f"[OCR] Extracting text from {os.path.basename(file_path)} (type={ext})")

    if ext == ".pdf":
        result = PDFTextExtractor()._run(file_path)
        log.info(f"[OCR] PDF extraction done — {len(result)} chars")
        return result

    # For images: try LLaVA first (much better than Tesseract for invoices)
    log.info(f"[OCR] Trying LLaVA vision model at {ollama_url}")
    result = extract_image_with_llava(file_path, ollama_url)
    if not result.startswith("Error"):
        log.info(f"[OCR] LLaVA extraction done — {len(result)} chars")
        return result

    log.warning(f"[OCR] LLaVA failed ({result[:100]}), falling back to Tesseract")
    result = ImageTextExtractor()._run(file_path)
    log.info(f"[OCR] Tesseract extraction done — {len(result)} chars")
    return result


def _resolve_model_config(user_id: str | None) -> "ModelConfig":
    """
    Return a ModelConfig for the given user.
    Picks the row with status='active' first; falls back to process env.
    Never mutates os.environ — safe for concurrent threads.
    """
    from invoice_processing_automation_system.crew import ModelConfig
    if user_id:
        try:
            from models import UserModelConfig
            db_tmp = SessionLocal()
            # Prefer active config; fall back to most recently updated
            ucfg = (
                db_tmp.query(UserModelConfig)
                .filter(UserModelConfig.user_id == user_id, UserModelConfig.status == "active")
                .first()
            )
            if not ucfg:
                ucfg = (
                    db_tmp.query(UserModelConfig)
                    .filter(UserModelConfig.user_id == user_id)
                    .order_by(UserModelConfig.updated_at.desc())
                    .first()
                )
            db_tmp.close()
            if ucfg and ucfg.model_name:
                user_model = ucfg.model_name
                is_ollama = user_model.startswith("ollama/")
                default = ModelConfig.from_env()
                real_key = ucfg.api_key if (ucfg.api_key and ucfg.api_key != "***") else None
                resolved = ModelConfig(
                    model=user_model,
                    base_url=ucfg.base_url or (default.base_url if is_ollama else None),
                    api_key=real_key or (None if is_ollama else default.api_key),
                )
                log.info(f"[Model] User {user_id[:8]}… → {ucfg.status} config: {resolved.describe()}")
                return resolved
            else:
                log.info(f"[Model] User {user_id[:8]}… → no active config, using system default")
        except Exception as e:
            log.warning(f"[Model] Could not load user model config for {user_id}: {e} — falling back to env default")

    cfg = ModelConfig.from_env()
    log.info(f"[Model] Using system default: {cfg.describe()}")
    return cfg



def _run_crew(ocr_text: str, file_path: str, user_id: str = None) -> dict | None:
    from invoice_processing_automation_system.crew import InvoiceProcessingAutomationSystemCrew

    model_cfg = _resolve_model_config(user_id)
    log.info(f"[Crew] Starting invoice extraction — model: {model_cfg.describe()}, file: {os.path.basename(file_path)}, ocr_chars: {len(ocr_text)}")

    crew_instance = (
        InvoiceProcessingAutomationSystemCrew()
        .set_model_config(model_cfg)
    )

    try:
        result = crew_instance.crew_minimal(
            erp_system="pending_approval",
            notification_channel="none",
        ).kickoff(inputs={
            "intake_source": f"Files to process:\n{file_path}",
            "ocr_text": ocr_text,
            "erp_system": "pending_approval",
            "notification_channel": "none",
        })
    except Exception as e:
        log.error(f"[Crew] Crew kickoff failed with model {model_cfg.describe()}: {e}")
        raise

    # Best source: step callback captured the full JSON before CrewAI truncated .raw
    if crew_instance._captured_extraction:
        log.info(f"[Crew] ✓ Using step-callback captured JSON — keys: {list(crew_instance._captured_extraction.keys())[:6]}")
        return crew_instance._captured_extraction

    tasks_output = result.tasks_output or []
    log.info(f"[Crew] Crew finished — {len(tasks_output)} task outputs")

    real_keys = {"invoice_number", "sender", "receiver", "line_items", "total_amount", "subtotal"}
    refusal_keys = {"status", "message", "error", "result"}

    def is_valid_invoice(d: dict) -> bool:
        return bool(real_keys & set(d.keys()))

    def is_refusal(d: dict) -> bool:
        return not is_valid_invoice(d) and bool(refusal_keys & set(d.keys()))

    # Task order: [0] extraction, [1] validation (intake agent removed — OCR done before crew)
    if len(tasks_output) > 0:
        task1 = tasks_output[0]

        # json_dict: CrewAI auto-parses valid JSON responses into this — most reliable
        if task1.json_dict and isinstance(task1.json_dict, dict) and is_valid_invoice(task1.json_dict):
            log.info(f"[Crew] ✓ Got invoice JSON from task[0].json_dict (extraction) — keys: {list(task1.json_dict.keys())[:6]}")
            return task1.json_dict

        # raw: fallback for models that wrap JSON in text or truncate
        raw1 = task1.raw
        parsed = _parse_json(raw1)
        if parsed is None:
            log.warning(f"[Crew] task[0] _parse_json returned None — raw length={len(raw1)}, preview: {raw1[:200]!r}")
        if parsed and isinstance(parsed, dict):
            if is_refusal(parsed):
                log.warning(f"[Crew] task[0] returned a refusal: {list(parsed.keys())} — trying fallback")
            elif is_valid_invoice(parsed):
                log.info(f"[Crew] ✓ Parsed invoice JSON from task[0].raw (extraction) — keys: {list(parsed.keys())[:6]}")
                return parsed

    # Fallback: scan all task outputs
    for i, task_out in enumerate(tasks_output):
        if task_out.json_dict and isinstance(task_out.json_dict, dict) and is_valid_invoice(task_out.json_dict):
            log.info(f"[Crew] ✓ Got invoice JSON from task[{i}].json_dict fallback")
            return task_out.json_dict
        parsed = _parse_json(task_out.raw)
        if parsed and isinstance(parsed, dict) and is_valid_invoice(parsed):
            log.info(f"[Crew] ✓ Parsed invoice JSON from task[{i}].raw fallback")
            return parsed

    # Last resort: crew result object
    if hasattr(result, 'json_dict') and result.json_dict and isinstance(result.json_dict, dict) and is_valid_invoice(result.json_dict):
        log.info("[Crew] ✓ Got invoice JSON from result.json_dict")
        return result.json_dict

    parsed = _parse_json(str(result.raw))
    if parsed and isinstance(parsed, dict) and is_valid_invoice(parsed):
        log.info("[Crew] ✓ Parsed invoice JSON from result.raw fallback")
        return parsed

    log.error(f"[Crew] ✗ Could not extract invoice JSON from any task output (count={len(tasks_output)})")
    for i, t in enumerate(tasks_output):
        log.error(f"[Crew]   task[{i}] json_dict={bool(t.json_dict)} raw preview (first 300): {t.raw[:300]!r}")
    return None



def _with_retry(fn, max_attempts: int = 3, delay: float = 2.0, label: str = ""):
    """Retry a function up to max_attempts times with exponential backoff."""
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if attempt < max_attempts:
                wait = delay * (2 ** (attempt - 1))
                log.warning(f"{label} attempt {attempt}/{max_attempts} failed: {e} — retrying in {wait:.1f}s")
                time.sleep(wait)
            else:
                log.error(f"{label} failed after {max_attempts} attempts: {e}")
    raise last_err


MAX_JOB_RETRIES = 3  # jobs are retried up to 3 times before marked permanently failed


def _safe_str(v) -> str | None:
    """Convert any value to string for Text columns — handles dicts/lists."""
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def save_invoice_to_db(db, user_id: str, extracted: dict, file_name: str, source: str) -> Invoice:
    """Save extracted invoice JSON to the invoices table."""
    s = extracted.get("sender") or {}
    r = extracted.get("receiver") or {}
    sb = s.get("bank") or {}
    rb = r.get("bank") or {}

    invoice = Invoice(
        user_id=user_id,
        file_name=file_name,
        source=source,
        invoice_number=extracted.get("invoice_number"),
        invoice_date=extracted.get("invoice_date"),
        due_date=extracted.get("due_date"),
        delivery_date=extracted.get("delivery_date"),
        payment_terms=extracted.get("payment_terms"),
        payment_method=extracted.get("payment_method"),
        purchase_order=extracted.get("purchase_order"),
        reference=extracted.get("reference"),
        # Sender
        sender_name=s.get("name"),
        sender_address=s.get("address"),
        sender_city=s.get("city"),
        sender_state=s.get("state"),
        sender_zip=s.get("zip"),
        sender_country=s.get("country"),
        sender_email=s.get("email"),
        sender_phone=s.get("phone"),
        sender_website=s.get("website"),
        sender_tax_id=s.get("tax_id"),
        sender_vat_number=s.get("vat_number"),
        sender_registration=s.get("registration_number"),
        sender_bank_name=sb.get("bank_name"),
        sender_bank_account_holder=sb.get("account_holder"),
        sender_bank_account_number=sb.get("account_number"),
        sender_bank_iban=sb.get("iban"),
        sender_bank_swift=sb.get("swift_bic"),
        sender_bank_routing=sb.get("routing_number"),
        sender_bank_sort_code=sb.get("sort_code"),
        sender_bank_branch=sb.get("branch"),
        sender_bank_address=sb.get("bank_address"),
        # Receiver
        receiver_name=r.get("name"),
        receiver_address=r.get("address"),
        receiver_city=r.get("city"),
        receiver_state=r.get("state"),
        receiver_zip=r.get("zip"),
        receiver_country=r.get("country"),
        receiver_email=r.get("email"),
        receiver_phone=r.get("phone"),
        receiver_tax_id=r.get("tax_id"),
        receiver_vat_number=r.get("vat_number"),
        receiver_bank_name=rb.get("bank_name"),
        receiver_bank_account_holder=rb.get("account_holder"),
        receiver_bank_account_number=rb.get("account_number"),
        receiver_bank_iban=rb.get("iban"),
        receiver_bank_swift=rb.get("swift_bic"),
        receiver_bank_routing=rb.get("routing_number"),
        receiver_bank_sort_code=rb.get("sort_code"),
        receiver_bank_branch=rb.get("branch"),
        # Financials
        currency=extracted.get("currency"),
        exchange_rate=_safe_float(extracted.get("exchange_rate")),
        subtotal=_safe_float(extracted.get("subtotal")),
        discount_total=_safe_float(extracted.get("discount_total")),
        discount_percent=_safe_float(extracted.get("discount_percent")),
        tax_rate=_safe_float(extracted.get("tax_rate")),
        tax_amount=_safe_float(extracted.get("tax_amount")),
        tax_type=extracted.get("tax_type"),
        shipping=_safe_float(extracted.get("shipping")),
        handling=_safe_float(extracted.get("handling")),
        other_charges=_safe_float(extracted.get("other_charges")),
        total_amount=_safe_float(extracted.get("total_amount")),
        amount_paid=_safe_float(extracted.get("amount_paid")),
        amount_due=_safe_float(extracted.get("amount_due")),
        deposit=_safe_float(extracted.get("deposit")),
        notes=_safe_str(extracted.get("notes")),
        terms_and_conditions=_safe_str(extracted.get("terms_and_conditions")),
        ocr_confidence=extracted.get("confidence"),
        full_json=extracted,
        approval_status="PENDING",
    )
    db.add(invoice)
    db.flush()  # get invoice.id

    # Save line items
    for item in (extracted.get("line_items") or []):
        # discount_amount takes priority; fall back to discount_percent as a raw value
        discount_val = _safe_float(item.get("discount_amount")) or _safe_float(item.get("discount_percent"))
        li = InvoiceLineItem(
            invoice_id=invoice.id,
            description=item.get("description"),
            quantity=_safe_float(item.get("quantity")),
            unit=item.get("unit"),
            unit_price=_safe_float(item.get("unit_price")),
            discount=discount_val,
            total=_safe_float(item.get("total")),
        )
        db.add(li)

    db.commit()
    return invoice


def process_job(job: ProcessingJob, db) -> bool:
    """Process a single queued job with retry logic."""
    log.info(f"[Job {job.id[:8]}] ── START ── file={job.file_name} source={job.source} attempt={job.retry_count + 1}/{MAX_JOB_RETRIES}")

    job.status = "processing"
    job.started_at = datetime.utcnow()
    db.commit()

    try:
        if not job.file_path or not os.path.exists(job.file_path):
            if job.email_message_id and job.source == "email":
                log.warning(f"[Job {job.id[:8]}] Temp file missing — attempting re-download from email")
                recovered = _redownload_attachment(job, db)
                if not recovered:
                    raise FileNotFoundError(f"Temp file gone and email re-download failed: {job.file_path}")
                log.info(f"[Job {job.id[:8]}] Re-download successful: {job.file_path}")
            else:
                raise FileNotFoundError(f"File not found (no email source to recover from): {job.file_path}")

        # ── Step 1: OCR ───────────────────────────────────────────────────────
        log.info(f"[Job {job.id[:8]}] Step 1/3 — OCR")
        ocr_text = _with_retry(
            lambda: _extract_ocr_async(job.file_path),
            max_attempts=2, delay=1.0, label=f"OCR job {job.id[:8]}"
        )
        log.info(f"[Job {job.id[:8]}] OCR complete — {len(ocr_text)} chars extracted")

        if len(ocr_text.strip()) < 20:
            log.warning(f"[Job {job.id[:8]}] OCR returned very little text ({len(ocr_text)} chars) — extraction may be poor")
        else:
            log.debug(f"[Job {job.id[:8]}] OCR preview: {ocr_text[:300]!r}")

        # ── Step 2: AI extraction ─────────────────────────────────────────────
        user_lock = _get_user_lock(job.user_id)
        log.info(f"[Job {job.id[:8]}] Step 2/3 — AI extraction (waiting for user slot)")
        with user_lock:
            log.info(f"[Job {job.id[:8]}] AI slot acquired — running crew")
            extracted = _with_retry(
                lambda: _run_crew(ocr_text, job.file_path, user_id=job.user_id),
                max_attempts=2, delay=5.0, label=f"AI crew job {job.id[:8]}"
            )

        if not extracted:
            raise ValueError("AI crew returned no structured data — check model connectivity and OCR output")

        log.info(f"[Job {job.id[:8]}] AI extraction complete — invoice_number={extracted.get('invoice_number')!r} total={extracted.get('total_amount')!r}")

        # ── Step 3: Coerce → Validate → Save ─────────────────────────────────
        log.info(f"[Job {job.id[:8]}] Step 3/3 — Coercion, Validation & DB save")
        extracted = _coerce_extracted(extracted)
        extracted = _validate_and_correct(extracted)
        issues = extracted.get("validation_issues", [])
        if issues:
            log.info(f"[Job {job.id[:8]}] Validation: {len(issues)} calc fix(es) applied — {[i['field'] for i in issues]}")
        else:
            log.info(f"[Job {job.id[:8]}] Validation: all calculations OK")

        try:
            invoice = save_invoice_to_db(db, job.user_id, extracted, job.file_name, job.source)
        except Exception as save_err:
            db.rollback()
            log.error(f"[Job {job.id[:8]}] DB save failed: {save_err}")
            raise save_err

        job.status = "done"
        job.invoice_id = invoice.id
        job.completed_at = datetime.utcnow()
        db.commit()

        elapsed = (job.completed_at - job.started_at).total_seconds()
        log.info(f"[Job {job.id[:8]}] ── DONE ── invoice={invoice.id[:8]} status=PENDING elapsed={elapsed:.1f}s")
        return True

    except Exception as e:
        import traceback
        log.error(f"[Job {job.id[:8]}] ── FAILED ── {type(e).__name__}: {e}")
        log.debug(f"[Job {job.id[:8]}] Traceback:\n{traceback.format_exc()}")
        try:
            db.rollback()
            job.retry_count = (job.retry_count or 0) + 1
            if job.retry_count < MAX_JOB_RETRIES:
                job.status = "queued"
                job.error_message = f"Attempt {job.retry_count} failed: {type(e).__name__}: {str(e)[:500]}"
                log.info(f"[Job {job.id[:8]}] Requeued for retry ({job.retry_count}/{MAX_JOB_RETRIES})")
            else:
                job.status = "failed"
                job.error_message = f"Permanently failed after {MAX_JOB_RETRIES} attempts. Last: {type(e).__name__}: {str(e)[:500]}"
                log.error(f"[Job {job.id[:8]}] Permanently failed after {MAX_JOB_RETRIES} attempts")
            job.completed_at = datetime.utcnow()
            db.commit()
        except Exception as inner:
            log.error(f"[Job {job.id[:8]}] Failed to update job status after failure: {inner}")
        return False


def run_worker_cycle():
    """
    Pick up queued jobs and process them in parallel across users.
    - One job per user at a time (per-user lock in process_job)
    - Multiple users processed simultaneously
    - OCR runs in parallel thread pool
    """
    db = SessionLocal()
    try:
        # Get one queued job per user (FIFO within each user) — simple approach
        # Get all queued jobs, group by user, take oldest per user
        all_queued = (
            db.query(ProcessingJob)
            .filter(ProcessingJob.status == "queued")
            .order_by(ProcessingJob.created_at)
            .all()
        )
        db.close()

        # Pick one job per user (oldest first)
        seen_users = set()
        jobs = []
        for job in all_queued:
            if job.user_id not in seen_users:
                seen_users.add(job.user_id)
                jobs.append(job)

        if not jobs:
            return

        log.info(f"Processing {len(jobs)} job(s) across {len(set(j.user_id for j in jobs))} user(s)")

        # Process each user's job in a separate thread
        def process_in_thread(job_id: str):
            thread_db = SessionLocal()
            thread_job = None
            try:
                thread_job = thread_db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
                if thread_job and thread_job.status == "queued":
                    process_job(thread_job, thread_db)
            except Exception as e:
                log.error(f"Thread error for job {job_id}: {e}")
                try:
                    thread_db.rollback()
                    if thread_job:
                        thread_job.status = "failed"
                        thread_job.error_message = str(e)[:500]
                        thread_job.completed_at = datetime.utcnow()
                        thread_db.commit()
                except Exception:
                    pass
            finally:
                thread_db.close()

        # Submit all jobs to thread pool and wait for completion
        with ThreadPoolExecutor(max_workers=min(len(jobs), 4), thread_name_prefix="job") as executor:
            futures = {executor.submit(process_in_thread, job.id): job.id for job in jobs}
            for future in as_completed(futures):
                job_id = futures[future]
                try:
                    future.result()
                except Exception as e:
                    log.error(f"Job {job_id} thread raised: {e}")

    except Exception as e:
        log.error(f"Worker cycle error: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        try:
            db.close()
        except Exception:
            pass


def worker_loop(poll_interval_seconds: int = 5):
    """Main loop — checks for queued jobs every N seconds."""
    global _running
    _running = True
    log.info("Invoice worker started")

    # On startup: reset any jobs stuck in 'processing' state (server was killed mid-job)
    _reset_stuck_jobs()

    while _running:
        try:
            run_worker_cycle()
            # Periodically check for stuck jobs (every 5 minutes)
            _check_stuck_jobs()
        except Exception as e:
            log.error(f"Worker cycle error: {e}")
        time.sleep(poll_interval_seconds)
    log.info("Invoice worker stopped")


_last_stuck_check = 0
STUCK_JOB_TIMEOUT_MINUTES = 15  # jobs processing longer than this are considered stuck


def _reset_stuck_jobs():
    """Reset jobs stuck in 'processing' state back to 'queued' on startup."""
    db = SessionLocal()
    try:
        stuck = db.query(ProcessingJob).filter(ProcessingJob.status == "processing").all()
        if stuck:
            log.warning(f"Found {len(stuck)} stuck job(s) in 'processing' state — resetting to 'queued'")
            for job in stuck:
                job.status = "queued"
                job.error_message = f"Reset: server restarted while processing (attempt {job.retry_count})"
            db.commit()
    except Exception as e:
        log.error(f"Failed to reset stuck jobs: {e}")
    finally:
        db.close()


def _check_stuck_jobs():
    """Periodically reset jobs that have been processing too long."""
    global _last_stuck_check
    now = time.time()
    if now - _last_stuck_check < 300:  # check every 5 minutes
        return
    _last_stuck_check = now

    db = SessionLocal()
    try:
        cutoff = datetime.utcnow().__class__.utcnow() - __import__("datetime").timedelta(minutes=STUCK_JOB_TIMEOUT_MINUTES)
        stuck = db.query(ProcessingJob).filter(
            ProcessingJob.status == "processing",
            ProcessingJob.started_at < cutoff,
        ).all()
        if stuck:
            log.warning(f"Watchdog: found {len(stuck)} job(s) stuck for >{STUCK_JOB_TIMEOUT_MINUTES}min — resetting")
            for job in stuck:
                job.retry_count = (job.retry_count or 0) + 1
                if job.retry_count >= MAX_JOB_RETRIES:
                    job.status = "failed"
                    job.error_message = f"Timed out after {STUCK_JOB_TIMEOUT_MINUTES} minutes"
                else:
                    job.status = "queued"
                    job.error_message = f"Watchdog reset: stuck for >{STUCK_JOB_TIMEOUT_MINUTES}min (attempt {job.retry_count})"
            db.commit()
    except Exception as e:
        log.error(f"Watchdog check failed: {e}")
    finally:
        db.close()


def start_worker(poll_interval_seconds: int = 5) -> Thread:
    """Start worker in a background thread."""
    t = Thread(target=worker_loop, args=(poll_interval_seconds,), daemon=True, name="invoice-worker")
    t.start()
    return t


def stop_worker():
    global _running
    _running = False


if __name__ == "__main__":
    worker_loop()
