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
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    for pat in [r"```(?:json)?\s*(\{.*?\})\s*```", r"(\{[\s\S]*\})"]:
        m = re.search(pat, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
    return None


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

        mail.login(cfg.username, cfg.password)
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

    # Try LLaVA vision model first, fall back to Tesseract
    log.info(f"[OCR] Trying LLaVA vision model at {ollama_url}")
    result = extract_image_with_llava(file_path, ollama_url)
    if result.startswith("Error"):
        log.warning(f"[OCR] LLaVA failed ({result[:100]}), falling back to Tesseract")
        result = ImageTextExtractor()._run(file_path)
        log.info(f"[OCR] Tesseract extraction done — {len(result)} chars")
    else:
        log.info(f"[OCR] LLaVA extraction done — {len(result)} chars")
    return result


def _resolve_model_config(user_id: str | None) -> "ModelConfig":
    """
    Return a ModelConfig for the given user.
    Checks user_model_configs table first; falls back to process env.
    Never mutates os.environ — safe for concurrent threads.
    """
    from invoice_processing_automation_system.crew import ModelConfig
    if user_id:
        try:
            from models import UserModelConfig
            db_tmp = SessionLocal()
            ucfg = db_tmp.query(UserModelConfig).filter(UserModelConfig.user_id == user_id).first()
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
                log.info(f"[Model] User {user_id[:8]}… → custom config: {resolved.describe()}")
                return resolved
            else:
                log.info(f"[Model] User {user_id[:8]}… → no custom config, using system default")
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

    tasks_output = result.tasks_output or []
    log.info(f"[Crew] Crew finished — {len(tasks_output)} task outputs")

    # Task order: [0] intake, [1] extraction, [2] validation
    # Try index 1 (structured_data_extraction) first — most reliable
    if len(tasks_output) > 1:
        parsed = _parse_json(tasks_output[1].raw)
        if parsed and isinstance(parsed, dict):
            log.info(f"[Crew] ✓ Parsed invoice JSON from task[1] (structured_data_extraction) — keys: {list(parsed.keys())[:6]}")
            return parsed

    # Fallback: scan all task outputs for valid invoice JSON
    for i, task_out in enumerate(tasks_output):
        parsed = _parse_json(task_out.raw)
        if parsed and isinstance(parsed, dict) and ("invoice_number" in parsed or "sender" in parsed or "line_items" in parsed):
            log.info(f"[Crew] ✓ Parsed invoice JSON from task[{i}] fallback")
            return parsed

    # Last resort: try the final crew result
    parsed = _parse_json(str(result.raw))
    if parsed and isinstance(parsed, dict):
        log.info("[Crew] ✓ Parsed invoice JSON from result.raw fallback")
        return parsed

    log.error(f"[Crew] ✗ Could not extract invoice JSON from any task output (count={len(tasks_output)})")
    for i, t in enumerate(tasks_output):
        log.error(f"[Crew]   task[{i}] raw preview: {t.raw[:300]!r}")
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
        li = InvoiceLineItem(
            invoice_id=invoice.id,
            description=item.get("description"),
            quantity=_safe_float(item.get("quantity")),
            unit=item.get("unit"),
            unit_price=_safe_float(item.get("unit_price")),
            discount=_safe_float(item.get("discount")),
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

        # ── Step 3: Validate & save ───────────────────────────────────────────
        log.info(f"[Job {job.id[:8]}] Step 3/3 — Validation & DB save")
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
                job.error_message = f"Attempt {job.retry_count} failed: {type(e).__name__}: {str(e)[:250]}"
                log.info(f"[Job {job.id[:8]}] Requeued for retry ({job.retry_count}/{MAX_JOB_RETRIES})")
            else:
                job.status = "failed"
                job.error_message = f"Permanently failed after {MAX_JOB_RETRIES} attempts. Last: {type(e).__name__}: {str(e)[:250]}"
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
