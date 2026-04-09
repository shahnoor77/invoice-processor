"""
Email Poller Scheduler — polls each user's IMAP inbox for invoice emails.
- Auto-detects IMAP settings from email domain
- Filters by invoice-related subjects and file types
- Validates attachments are likely invoices before queuing
- Marks emails as read after processing
- Uses FIFO queue (ordered by email date)
"""
import email
import imaplib
import logging
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from email.header import decode_header
from threading import Thread

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from dotenv import load_dotenv
load_dotenv(override=True)

from database import SessionLocal
from models import EmailConfig, ProcessingJob

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SCHEDULER] %(message)s")
log = logging.getLogger("scheduler")

_running = False

# Supported invoice attachment types
INVOICE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp", ".heic"}

# Keywords that suggest an email contains an invoice
INVOICE_SUBJECT_KEYWORDS = [
    "invoice", "inv-", "inv_", "bill", "billing", "receipt", "statement",
    "payment", "purchase order", "po-", "po_", "remittance", "payable",
    "فاتورة", "rechnung", "factura", "facture",  # multilingual
]

# Keywords in filename that suggest it's an invoice
INVOICE_FILENAME_KEYWORDS = [
    "invoice", "inv", "bill", "receipt", "statement", "payment",
    "purchase", "order", "po", "remittance",
]

# Filenames/patterns to SKIP (not invoices)
SKIP_FILENAME_PATTERNS = [
    "signature", "logo", "banner", "header", "footer", "avatar",
    "profile", "photo", "image", "pic", "thumb", "icon",
]


def _decode_str(value: str) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)


def _is_invoice_subject(subject: str) -> bool:
    """Check if email subject suggests it contains an invoice."""
    s = subject.lower()
    return any(kw in s for kw in INVOICE_SUBJECT_KEYWORDS)


def _is_invoice_filename(filename: str) -> bool:
    """Check if attachment filename looks like an invoice."""
    if not filename:
        return False
    name_lower = filename.lower()
    ext = os.path.splitext(name_lower)[-1]

    # Must be a supported file type
    if ext not in INVOICE_EXTENSIONS:
        return False

    # Skip obvious non-invoice files
    if any(skip in name_lower for skip in SKIP_FILENAME_PATTERNS):
        return False

    # If filename contains invoice keywords, definitely include
    if any(kw in name_lower for kw in INVOICE_FILENAME_KEYWORDS):
        return True

    # PDFs are almost always invoices in a business context
    if ext == ".pdf":
        return True

    # For images, require invoice keyword in filename or subject
    return False


def _build_imap_search(config: EmailConfig) -> str:
    """Build IMAP search criteria — fetch unread emails, optionally filter by subject."""
    criteria = ["UNSEEN"]
    # Add subject keyword filter using OR for multiple keywords
    # IMAP OR is limited, use a broad search and filter locally
    return " ".join(criteria)


def poll_user_emails(config: EmailConfig, db) -> int:
    """Poll one user's IMAP inbox. Returns number of new jobs queued."""
    queued = 0
    try:
        # Connect using stored IMAP settings
        if config.imap_encryption in ("SSL/TLS", "SSL"):
            mail = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
        else:
            mail = imaplib.IMAP4(config.imap_host, config.imap_port)
            if config.imap_encryption == "STARTTLS":
                mail.starttls()

        mail.login(config.username, config.password)
        mail.select(config.folder or "INBOX")

        # Search for unread emails
        _, msg_ids = mail.search(None, "UNSEEN")
        ids = msg_ids[0].split()

        if not ids:
            mail.logout()
            return 0

        log.info(f"Found {len(ids)} unread email(s) for {config.email}")

        # Process in FIFO order (oldest first) up to max_emails_per_poll
        for msg_id in ids[:config.max_emails_per_poll]:
            try:
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                subject = _decode_str(msg.get("Subject", "(no subject)"))
                sender = _decode_str(msg.get("From", ""))
                date_str = msg.get("Date", "")

                # Check if subject suggests invoice — but don't skip if no subject match
                # (attachment check is the primary filter)
                subject_match = _is_invoice_subject(subject)

                attachments_found = 0
                for part in msg.walk():
                    content_disposition = part.get("Content-Disposition", "")
                    content_type = part.get_content_type()

                    # Check both attachments and inline images
                    is_attachment = "attachment" in content_disposition
                    is_inline_doc = "inline" in content_disposition and content_type in (
                        "application/pdf", "image/png", "image/jpeg", "image/tiff"
                    )

                    if not (is_attachment or is_inline_doc):
                        continue

                    filename = part.get_filename()
                    if not filename:
                        # Generate filename from content type
                        ext_map = {"application/pdf": ".pdf", "image/png": ".png",
                                   "image/jpeg": ".jpg", "image/tiff": ".tiff"}
                        ext = ext_map.get(content_type, "")
                        if ext:
                            filename = f"attachment_{msg_id.decode()}_{attachments_found}{ext}"
                        else:
                            continue

                    filename = _decode_str(filename)

                    # Validate it looks like an invoice file
                    if not _is_invoice_filename(filename):
                        # If subject strongly suggests invoice, include PDFs anyway
                        if subject_match and filename.lower().endswith(".pdf"):
                            pass  # include it
                        else:
                            log.debug(f"Skipping non-invoice attachment: {filename}")
                            continue

                    safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")

                    # Check for duplicates
                    existing = db.query(ProcessingJob).filter(
                        ProcessingJob.user_id == config.user_id,
                        ProcessingJob.file_name == safe_name,
                        ProcessingJob.email_subject == subject,
                        ProcessingJob.status.in_(["queued", "processing", "done"]),
                    ).first()

                    if existing:
                        log.debug(f"Skipping duplicate: {safe_name}")
                        continue

                    # Save attachment
                    tmp_dir = tempfile.mkdtemp(prefix="email_invoice_")
                    file_path = os.path.join(tmp_dir, safe_name)
                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue

                    with open(file_path, "wb") as f:
                        f.write(payload)

                    # Queue job
                    job = ProcessingJob(
                        user_id=config.user_id,
                        file_name=safe_name,
                        file_path=file_path,
                        source="email",
                        email_subject=subject,
                        email_sender=sender,
                        email_message_id=msg.get("Message-ID", ""),
                        status="queued",
                    )
                    db.add(job)
                    queued += 1
                    attachments_found += 1
                    log.info(f"Queued: {safe_name} | Subject: {subject[:50]} | From: {sender[:40]}")

                # Mark as read after processing
                if config.mark_as_read:
                    mail.store(msg_id, "+FLAGS", "\\Seen")

            except Exception as msg_err:
                log.error(f"Error processing message {msg_id}: {msg_err}")
                continue

        db.commit()
        mail.logout()

        # Update last polled timestamp
        config.last_polled_at = datetime.utcnow()
        db.commit()

    except imaplib.IMAP4.error as e:
        log.error(f"IMAP error for user {config.user_id} ({config.email}): {e}")
    except Exception as e:
        log.error(f"Poll error for user {config.user_id}: {e}")

    return queued


def run_poll_cycle():
    """Poll all active email configs in parallel — one thread per user."""
    db = SessionLocal()
    try:
        configs = db.query(EmailConfig).filter(EmailConfig.is_active == True).all()
        now = datetime.utcnow()

        due_configs = []
        for config in configs:
            if config.last_polled_at:
                elapsed = (now - config.last_polled_at).total_seconds() / 60
                if elapsed < config.poll_interval_minutes:
                    continue
            due_configs.append(config)

        db.close()

        if not due_configs:
            return

        # Poll each user's inbox in parallel
        def poll_in_thread(config_id: str):
            thread_db = SessionLocal()
            try:
                cfg = thread_db.query(EmailConfig).filter(EmailConfig.id == config_id).first()
                if cfg:
                    log.info(f"Polling emails for user {cfg.user_id} ({cfg.email})")
                    count = poll_user_emails(cfg, thread_db)
                    if count:
                        log.info(f"Queued {count} new invoice(s) for user {cfg.user_id}")
            except Exception as e:
                log.error(f"Poll thread error for config {config_id}: {e}")
            finally:
                thread_db.close()

        with ThreadPoolExecutor(max_workers=min(len(due_configs), 5), thread_name_prefix="poll") as executor:
            futures = [executor.submit(poll_in_thread, cfg.id) for cfg in due_configs]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    log.error(f"Poll future error: {e}")

    except Exception as e:
        log.error(f"Poll cycle error: {e}")
        try:
            db.close()
        except Exception:
            pass


def scheduler_loop(interval_seconds: int = 30):
    global _running
    _running = True
    log.info("Email scheduler started")
    while _running:
        try:
            run_poll_cycle()
        except Exception as e:
            log.error(f"Scheduler error: {e}")
        time.sleep(interval_seconds)
    log.info("Email scheduler stopped")


def start_scheduler(interval_seconds: int = 30) -> Thread:
    t = Thread(target=scheduler_loop, args=(interval_seconds,), daemon=True, name="email-scheduler")
    t.start()
    return t


def stop_scheduler():
    global _running
    _running = False


if __name__ == "__main__":
    scheduler_loop()
