"""
Email Poller Scheduler — polls each user's IMAP inbox for invoice emails.

Polling strategy (layered for reliability):
  1. UID-based: fetch all UIDs > last_seen_uid — catches everything since last run
  2. SINCE-date fallback: if no UID stored, search SINCE (last_polled_at - lookback window)
  3. UNSEEN safety net: always also fetch UNSEEN to catch manually-unread emails
  4. Message-ID dedup: never queue the same email twice regardless of read/unread state

This means:
  - Missed emails (server restart, network blip) are caught on next poll
  - Manually-marked-as-read emails are still processed
  - No duplicates even if the same email appears in multiple search results
"""
import email
import imaplib
import logging
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from email.header import decode_header
from threading import Thread

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from dotenv import load_dotenv
load_dotenv(override=True)

from database import SessionLocal
from models import EmailConfig, ProcessingJob

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("scheduler")

_running = False

# How far back to look for missed emails on first poll or after a gap
LOOKBACK_HOURS = 48

# Supported invoice attachment types
INVOICE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp", ".heic"}

INVOICE_SUBJECT_KEYWORDS = [
    "invoice", "inv-", "inv_", "bill", "billing", "receipt", "statement",
    "payment", "purchase order", "po-", "po_", "remittance", "payable",
    "فاتورة", "rechnung", "factura", "facture",
]

INVOICE_FILENAME_KEYWORDS = [
    "invoice", "inv", "bill", "receipt", "statement", "payment",
    "purchase", "order", "po", "remittance",
]

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
    s = subject.lower()
    return any(kw in s for kw in INVOICE_SUBJECT_KEYWORDS)


def _is_invoice_filename(filename: str) -> bool:
    if not filename:
        return False
    name_lower = filename.lower()
    ext = os.path.splitext(name_lower)[-1]
    if ext not in INVOICE_EXTENSIONS:
        return False
    if any(skip in name_lower for skip in SKIP_FILENAME_PATTERNS):
        return False
    if any(kw in name_lower for kw in INVOICE_FILENAME_KEYWORDS):
        return True
    if ext == ".pdf":
        return True
    return False


def _connect_imap(config: EmailConfig) -> imaplib.IMAP4:
    """Open and authenticate an IMAP connection."""
    from password_encryption import decrypt_password
    if config.imap_encryption in ("SSL/TLS", "SSL"):
        mail = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
    else:
        mail = imaplib.IMAP4(config.imap_host, config.imap_port)
        if config.imap_encryption == "STARTTLS":
            mail.starttls()
    mail.login(config.username, decrypt_password(config.password))
    return mail


def _fetch_candidate_uids(mail: imaplib.IMAP4, config: EmailConfig) -> list[bytes]:
    """
    Return a deduplicated list of IMAP UIDs to inspect.

    Strategy:
      A) If we have a last_seen_uid: fetch UID > last_seen_uid (catches everything new)
      B) SINCE date: look back LOOKBACK_HOURS from last_polled_at (catches missed emails)
      C) UNSEEN: always include unread (safety net for manually-unread emails)

    All three sets are unioned and deduplicated.
    """
    uid_set: set[bytes] = set()

    # A) UID-based: everything after the last processed UID
    if config.last_seen_uid:
        try:
            _, data = mail.uid("search", None, f"UID {config.last_seen_uid}:*")
            uids = data[0].split() if data[0] else []
            # Filter out the last_seen_uid itself (IMAP range is inclusive)
            uids = [u for u in uids if u.decode() != config.last_seen_uid]
            uid_set.update(uids)
            log.debug(f"[Poll] UID>{config.last_seen_uid}: {len(uids)} message(s)")
        except Exception as e:
            log.warning(f"[Poll] UID search failed: {e}")

    # B) SINCE date: look back from last poll (or LOOKBACK_HOURS if never polled)
    if config.last_polled_at:
        since_dt = config.last_polled_at - timedelta(hours=2)  # 2h overlap to catch stragglers
    else:
        since_dt = datetime.utcnow() - timedelta(hours=LOOKBACK_HOURS)

    since_str = since_dt.strftime("%d-%b-%Y")
    try:
        _, data = mail.uid("search", None, f"SINCE {since_str}")
        uids = data[0].split() if data[0] else []
        uid_set.update(uids)
        log.debug(f"[Poll] SINCE {since_str}: {len(uids)} message(s)")
    except Exception as e:
        log.warning(f"[Poll] SINCE search failed: {e}")

    # C) UNSEEN: always include unread emails regardless of date
    try:
        _, data = mail.uid("search", None, "UNSEEN")
        uids = data[0].split() if data[0] else []
        uid_set.update(uids)
        log.debug(f"[Poll] UNSEEN: {len(uids)} message(s)")
    except Exception as e:
        log.warning(f"[Poll] UNSEEN search failed: {e}")

    # Sort numerically so we process oldest first (FIFO)
    try:
        return sorted(uid_set, key=lambda u: int(u))
    except Exception:
        return list(uid_set)


def _already_queued(db, user_id: str, message_id: str) -> bool:
    """Check if this Message-ID was already queued/processed."""
    if not message_id:
        return False
    return db.query(ProcessingJob).filter(
        ProcessingJob.user_id == user_id,
        ProcessingJob.email_message_id == message_id,
        ProcessingJob.status.in_(["queued", "processing", "done"]),
    ).first() is not None


def poll_user_emails(config: EmailConfig, db) -> int:
    """Poll one user's IMAP inbox. Returns number of new jobs queued."""
    queued = 0
    max_uid_seen = config.last_seen_uid

    try:
        mail = _connect_imap(config)
        mail.select(config.folder or "INBOX")

        candidate_uids = _fetch_candidate_uids(mail, config)

        if not candidate_uids:
            log.info(f"[Poll] {config.email}: no new messages")
            mail.logout()
            _update_poll_timestamp(config, db, max_uid_seen)
            return 0

        log.info(f"[Poll] {config.email}: {len(candidate_uids)} candidate message(s) to inspect")

        processed_count = 0
        for uid in candidate_uids[:config.max_emails_per_poll]:
            try:
                _, msg_data = mail.uid("fetch", uid, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                subject = _decode_str(msg.get("Subject", "(no subject)"))
                sender = _decode_str(msg.get("From", ""))
                message_id = msg.get("Message-ID", "").strip()
                date_str = msg.get("Date", "")

                # Track highest UID seen regardless of whether we queue it
                uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
                if not max_uid_seen or int(uid_str) > int(max_uid_seen):
                    max_uid_seen = uid_str

                # Dedup by Message-ID — primary guard against reprocessing
                if _already_queued(db, config.user_id, message_id):
                    log.debug(f"[Poll] Skip (already queued): {message_id[:40]} | {subject[:40]}")
                    processed_count += 1
                    continue

                subject_match = _is_invoice_subject(subject)
                attachments_queued = 0

                for part in msg.walk():
                    content_disposition = part.get("Content-Disposition", "")
                    content_type = part.get_content_type()

                    is_attachment = "attachment" in content_disposition
                    is_inline_doc = "inline" in content_disposition and content_type in (
                        "application/pdf", "image/png", "image/jpeg", "image/tiff"
                    )

                    if not (is_attachment or is_inline_doc):
                        continue

                    filename = part.get_filename()
                    if not filename:
                        ext_map = {
                            "application/pdf": ".pdf", "image/png": ".png",
                            "image/jpeg": ".jpg", "image/tiff": ".tiff",
                        }
                        ext = ext_map.get(content_type, "")
                        if ext:
                            filename = f"attachment_{uid_str}_{attachments_queued}{ext}"
                        else:
                            continue

                    filename = _decode_str(filename)

                    if not _is_invoice_filename(filename):
                        if subject_match and filename.lower().endswith(".pdf"):
                            pass  # subject strongly suggests invoice — include anyway
                        else:
                            log.debug(f"[Poll] Skip non-invoice attachment: {filename}")
                            continue

                    safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")

                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue

                    tmp_dir = tempfile.mkdtemp(prefix="email_invoice_")
                    file_path = os.path.join(tmp_dir, safe_name)
                    with open(file_path, "wb") as f:
                        f.write(payload)

                    job = ProcessingJob(
                        user_id=config.user_id,
                        file_name=safe_name,
                        file_path=file_path,
                        source="email",
                        email_subject=subject,
                        email_sender=sender,
                        email_message_id=message_id,
                        status="queued",
                    )
                    db.add(job)
                    queued += 1
                    attachments_queued += 1
                    log.info(f"[Poll] Queued: {safe_name} | From: {sender[:40]} | Subject: {subject[:50]}")

                # Mark as read only after we've processed all attachments
                if config.mark_as_read and attachments_queued > 0:
                    mail.uid("store", uid, "+FLAGS", "\\Seen")

                processed_count += 1

            except Exception as msg_err:
                log.error(f"[Poll] Error processing UID {uid}: {msg_err}")
                continue

        db.commit()
        mail.logout()

        log.info(f"[Poll] {config.email}: inspected {processed_count}, queued {queued} new job(s)")

    except imaplib.IMAP4.error as e:
        log.error(f"[Poll] IMAP auth/connection error for {config.email}: {e}")
    except ConnectionRefusedError:
        log.error(f"[Poll] Connection refused for {config.email} ({config.imap_host}:{config.imap_port})")
    except Exception as e:
        log.error(f"[Poll] Unexpected error for {config.email}: {type(e).__name__}: {e}")

    _update_poll_timestamp(config, db, max_uid_seen)
    return queued


def _update_poll_timestamp(config: EmailConfig, db, max_uid_seen: str | None):
    """Persist last_polled_at and last_seen_uid."""
    try:
        config.last_polled_at = datetime.utcnow()
        if max_uid_seen:
            config.last_seen_uid = max_uid_seen
        db.commit()
    except Exception as e:
        log.warning(f"[Poll] Failed to update poll timestamp for {config.email}: {e}")


def run_poll_cycle():
    """Poll all active email configs in parallel — one thread per user."""
    db = SessionLocal()
    try:
        configs = db.query(EmailConfig).filter(EmailConfig.is_active == True).all()
        now = datetime.utcnow()

        due_configs = []
        for config in configs:
            if config.last_polled_at:
                elapsed_minutes = (now - config.last_polled_at).total_seconds() / 60
                if elapsed_minutes < config.poll_interval_minutes:
                    continue
            due_configs.append(config)

        db.close()

        if not due_configs:
            return

        log.info(f"[Scheduler] Polling {len(due_configs)} account(s)")

        def poll_in_thread(config_id: str):
            thread_db = SessionLocal()
            try:
                cfg = thread_db.query(EmailConfig).filter(EmailConfig.id == config_id).first()
                if cfg:
                    count = poll_user_emails(cfg, thread_db)
                    if count:
                        log.info(f"[Scheduler] {cfg.email}: {count} new invoice(s) queued")
            except Exception as e:
                log.error(f"[Scheduler] Poll thread error for config {config_id}: {e}")
            finally:
                thread_db.close()

        with ThreadPoolExecutor(max_workers=min(len(due_configs), 5), thread_name_prefix="poll") as executor:
            futures = [executor.submit(poll_in_thread, cfg.id) for cfg in due_configs]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    log.error(f"[Scheduler] Poll future error: {e}")

    except Exception as e:
        log.error(f"[Scheduler] Cycle error: {e}")
        try:
            db.close()
        except Exception:
            pass


def scheduler_loop(interval_seconds: int = 30):
    global _running
    _running = True
    log.info(f"[Scheduler] Email scheduler started (check interval={interval_seconds}s, lookback={LOOKBACK_HOURS}h)")
    while _running:
        try:
            run_poll_cycle()
        except Exception as e:
            log.error(f"[Scheduler] Loop error: {e}")
        time.sleep(interval_seconds)
    log.info("[Scheduler] Email scheduler stopped")


def start_scheduler(interval_seconds: int = 30) -> Thread:
    t = Thread(target=scheduler_loop, args=(interval_seconds,), daemon=True, name="email-scheduler")
    t.start()
    return t


def stop_scheduler():
    global _running
    _running = False


if __name__ == "__main__":
    scheduler_loop()
