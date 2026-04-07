"""
Email Poller Scheduler — runs every N minutes per user.
Checks each user's configured IMAP inbox for new invoice emails,
downloads attachments, and queues them as ProcessingJobs.

Run standalone: python scheduler.py
Or import and call start_scheduler() from api.py startup.
"""
import imaplib
import email
import logging
import os
import sys
import tempfile
import time
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

INVOICE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"}
INVOICE_KEYWORDS = ["invoice", "bill", "receipt", "statement", "payment", "inv-", "inv_"]

_running = False


def _decode_str(value: str) -> str:
    parts = decode_header(value)
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)


def _is_invoice_attachment(filename: str) -> bool:
    """Heuristic: check extension and filename keywords."""
    if not filename:
        return False
    ext = os.path.splitext(filename.lower())[-1]
    if ext not in INVOICE_EXTENSIONS:
        return False
    name_lower = filename.lower()
    # Accept all PDFs/images — they could be invoices
    # Could tighten this with keyword check if too many false positives
    return True


def poll_user_emails(config: EmailConfig, db) -> int:
    """
    Poll one user's IMAP inbox. Returns number of new jobs queued.
    """
    queued = 0
    try:
        # Connect
        if config.imap_encryption in ("SSL/TLS", "SSL"):
            mail = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
        else:
            mail = imaplib.IMAP4(config.imap_host, config.imap_port)
            if config.imap_encryption == "STARTTLS":
                mail.starttls()

        mail.login(config.username, config.password)
        mail.select(config.folder or "INBOX")

        # Search unread
        _, msg_ids = mail.search(None, "UNSEEN")
        ids = msg_ids[0].split()

        if not ids:
            mail.logout()
            return 0

        # Process up to max_emails_per_poll
        for msg_id in ids[-config.max_emails_per_poll:]:
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = _decode_str(msg.get("Subject", "(no subject)"))
            sender = _decode_str(msg.get("From", ""))

            for part in msg.walk():
                content_disposition = part.get("Content-Disposition", "")
                if "attachment" not in content_disposition:
                    continue

                filename = part.get_filename()
                if not filename or not _is_invoice_attachment(filename):
                    continue

                filename = _decode_str(filename)
                safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")

                # Save to temp file
                tmp_dir = tempfile.mkdtemp(prefix="email_invoice_")
                file_path = os.path.join(tmp_dir, safe_name)
                with open(file_path, "wb") as f:
                    f.write(part.get_payload(decode=True))

                # Check not already queued (avoid duplicates)
                existing = db.query(ProcessingJob).filter(
                    ProcessingJob.user_id == config.user_id,
                    ProcessingJob.file_name == safe_name,
                    ProcessingJob.email_subject == subject,
                    ProcessingJob.status.in_(["queued", "processing", "done"]),
                ).first()

                if existing:
                    log.info(f"Skipping duplicate: {safe_name} for user {config.user_id}")
                    continue

                # Create job
                job = ProcessingJob(
                    user_id=config.user_id,
                    file_name=safe_name,
                    file_path=file_path,
                    source="email",
                    email_subject=subject,
                    email_sender=sender,
                    status="queued",
                )
                db.add(job)
                queued += 1
                log.info(f"Queued: {safe_name} from {sender} for user {config.user_id}")

            # Mark as read if configured
            if config.mark_as_read:
                mail.store(msg_id, "+FLAGS", "\\Seen")

        db.commit()
        mail.logout()

        # Update last polled
        config.last_polled_at = datetime.utcnow()
        db.commit()

    except imaplib.IMAP4.error as e:
        log.error(f"IMAP error for user {config.user_id}: {e}")
    except Exception as e:
        log.error(f"Poll error for user {config.user_id}: {e}")

    return queued


def run_poll_cycle():
    """Poll all active email configs that are due for polling."""
    db = SessionLocal()
    try:
        configs = db.query(EmailConfig).filter(EmailConfig.is_active == True).all()
        now = datetime.utcnow()

        for config in configs:
            # Check if due
            if config.last_polled_at:
                elapsed = (now - config.last_polled_at).total_seconds() / 60
                if elapsed < config.poll_interval_minutes:
                    continue

            log.info(f"Polling emails for user {config.user_id} ({config.email})")
            count = poll_user_emails(config, db)
            if count:
                log.info(f"Queued {count} new invoice(s) for user {config.user_id}")
    finally:
        db.close()


def scheduler_loop(interval_seconds: int = 60):
    """Main loop — checks every minute if any user is due for polling."""
    global _running
    _running = True
    log.info("Email scheduler started")
    while _running:
        try:
            run_poll_cycle()
        except Exception as e:
            log.error(f"Scheduler cycle error: {e}")
        time.sleep(interval_seconds)
    log.info("Email scheduler stopped")


def start_scheduler(interval_seconds: int = 60) -> Thread:
    """Start scheduler in a background thread. Returns the thread."""
    t = Thread(target=scheduler_loop, args=(interval_seconds,), daemon=True, name="email-scheduler")
    t.start()
    return t


def stop_scheduler():
    global _running
    _running = False


if __name__ == "__main__":
    scheduler_loop()
