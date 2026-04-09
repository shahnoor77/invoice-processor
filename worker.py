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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [WORKER] %(message)s")
log = logging.getLogger("worker")

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

    if ext == ".pdf":
        return PDFTextExtractor()._run(file_path)

    # Try LLaVA vision model first, fall back to Tesseract
    result = extract_image_with_llava(file_path, ollama_url)
    if result.startswith("Error"):
        result = ImageTextExtractor()._run(file_path)
    return result
    from invoice_processing_automation_system.tools.custom_tool import (
        PDFTextExtractor, ImageTextExtractor, extract_image_with_llava
    )
    ext = os.path.splitext(file_path)[-1].lower()
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://110.39.187.178:11434")

    if ext == ".pdf":
        return PDFTextExtractor()._run(file_path)

    result = extract_image_with_llava(file_path, ollama_url)
    if result.startswith("Error"):
        result = ImageTextExtractor()._run(file_path)
    return result


def _run_crew(ocr_text: str, file_path: str, user_id: str = None) -> dict | None:
    from invoice_processing_automation_system.crew import InvoiceProcessingAutomationSystemCrew

    # Apply per-user model config if available
    if user_id:
        try:
            from models import UserModelConfig
            db_tmp = SessionLocal()
            ucfg = db_tmp.query(UserModelConfig).filter(UserModelConfig.user_id == user_id).first()
            if ucfg:
                if ucfg.model_name:
                    os.environ["MODEL"] = ucfg.model_name
                if ucfg.api_key:
                    os.environ["MODEL_API_KEY"] = ucfg.api_key
                if ucfg.base_url:
                    os.environ["OLLAMA_BASE_URL"] = ucfg.base_url
                    os.environ["OLLAMA_API_BASE"] = ucfg.base_url
            db_tmp.close()
        except Exception:
            pass

    result = InvoiceProcessingAutomationSystemCrew().crew().kickoff(inputs={
        "intake_source": f"Files to process:\n{file_path}",
        "ocr_text": ocr_text,
        "erp_system": "pending_approval",
        "notification_channel": "none",
    })
    for task_output in (result.tasks_output or []):
        if hasattr(task_output, "name") and task_output.name == "structured_data_extraction":
            return _parse_json(task_output.raw)
    return _parse_json(str(result.raw))


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
    log.info(f"Processing job {job.id}: {job.file_name} (attempt {job.retry_count + 1}/{MAX_JOB_RETRIES})")

    job.status = "processing"
    job.started_at = datetime.utcnow()
    db.commit()

    try:
        if not job.file_path or not os.path.exists(job.file_path):
            # Try to re-download from email if we have the message ID
            if job.email_message_id and job.source == "email":
                log.info(f"Job {job.id}: temp file missing, attempting re-download from email")
                recovered = _redownload_attachment(job, db)
                if not recovered:
                    raise FileNotFoundError(f"Temp file gone and re-download failed: {job.file_path}")
            else:
                raise FileNotFoundError(f"File not found and no email source to recover from: {job.file_path}")

        # OCR with retry
        log.info(f"Job {job.id}: starting OCR")
        ocr_text = _with_retry(
            lambda: _extract_ocr_async(job.file_path),
            max_attempts=2, delay=1.0, label=f"OCR job {job.id}"
        )

        # AI crew with per-user lock and retry
        user_lock = _get_user_lock(job.user_id)
        log.info(f"Job {job.id}: waiting for user AI slot")
        with user_lock:
            log.info(f"Job {job.id}: running AI crew")
            extracted = _with_retry(
                lambda: _run_crew(ocr_text, job.file_path, user_id=job.user_id),
                max_attempts=2, delay=5.0, label=f"AI crew job {job.id}"
            )

        if not extracted:
            raise ValueError("AI crew returned no structured data")

        # Save to DB
        try:
            invoice = save_invoice_to_db(db, job.user_id, extracted, job.file_name, job.source)
        except Exception as save_err:
            db.rollback()
            raise save_err

        job.status = "done"
        job.invoice_id = invoice.id
        job.completed_at = datetime.utcnow()
        db.commit()

        log.info(f"Job {job.id} done → Invoice {invoice.id} (PENDING)")
        return True

    except Exception as e:
        log.error(f"Job {job.id} failed: {e}")
        try:
            db.rollback()
            job.retry_count = (job.retry_count or 0) + 1
            if job.retry_count < MAX_JOB_RETRIES:
                # Requeue for retry
                job.status = "queued"
                job.error_message = f"Attempt {job.retry_count} failed: {str(e)[:300]}"
                log.info(f"Job {job.id} requeued (attempt {job.retry_count}/{MAX_JOB_RETRIES})")
            else:
                # Permanently failed
                job.status = "failed"
                job.error_message = f"Failed after {MAX_JOB_RETRIES} attempts. Last error: {str(e)[:300]}"
                log.error(f"Job {job.id} permanently failed after {MAX_JOB_RETRIES} attempts")
            job.completed_at = datetime.utcnow()
            db.commit()
        except Exception as inner:
            log.error(f"Failed to update job status: {inner}")
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
