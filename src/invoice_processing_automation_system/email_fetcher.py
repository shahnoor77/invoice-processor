"""IMAP email fetcher — reads invoice attachments from any email provider."""
import email
import imaplib
import os
import tempfile
from email.header import decode_header
from typing import List, Tuple

IMAP_SERVERS = {
    "gmail.com": ("imap.gmail.com", 993),
    "googlemail.com": ("imap.gmail.com", 993),
    "outlook.com": ("outlook.office365.com", 993),
    "hotmail.com": ("outlook.office365.com", 993),
    "live.com": ("outlook.office365.com", 993),
    "yahoo.com": ("imap.mail.yahoo.com", 993),
    "yahoo.co.uk": ("imap.mail.yahoo.com", 993),
}

INVOICE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def _get_imap_server(email_address: str) -> Tuple[str, int]:
    domain = email_address.split("@")[-1].lower()
    return IMAP_SERVERS.get(domain, (f"imap.{domain}", 993))


def _decode_str(value: str) -> str:
    parts = decode_header(value)
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def fetch_invoice_emails(
    email_address: str,
    password: str,
    max_emails: int = 10,
    unread_only: bool = True,
    from_filter: str = "",
    subject_filter: str = "",
    since_date: str = "",
) -> Tuple[List[dict], str]:
    """
    Connect via IMAP and fetch emails with invoice attachments.

    Args:
        from_filter: filter by sender email/domain e.g. "vendor@acme.com"
        subject_filter: filter by subject keyword e.g. "invoice"
        since_date: filter emails since date e.g. "01-Jan-2024" (DD-Mon-YYYY)

    Returns:
        (list of {subject, sender, date, attachments: [{name, path}]}, error_message)
    """
    host, port = _get_imap_server(email_address)
    results = []

    try:
        mail = imaplib.IMAP4_SSL(host, port)
        mail.login(email_address, password)
        mail.select("INBOX")

        # Build IMAP search criteria
        criteria = []
        if unread_only:
            criteria.append("UNSEEN")
        if from_filter.strip():
            criteria.append(f'FROM "{from_filter.strip()}"')
        if subject_filter.strip():
            criteria.append(f'SUBJECT "{subject_filter.strip()}"')
        if since_date.strip():
            criteria.append(f'SINCE "{since_date.strip()}"')

        search_str = " ".join(criteria) if criteria else "ALL"
        _, msg_ids = mail.search(None, search_str)
        ids = msg_ids[0].split()

        if not ids:
            mail.logout()
            return [], None

        for msg_id in reversed(ids[-max_emails:]):
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = _decode_str(msg.get("Subject", "(no subject)"))
            sender = _decode_str(msg.get("From", ""))
            date = msg.get("Date", "")

            attachments = []
            for part in msg.walk():
                content_disposition = part.get("Content-Disposition", "")
                if "attachment" not in content_disposition:
                    continue
                filename = part.get_filename()
                if not filename:
                    continue
                filename = _decode_str(filename)
                ext = os.path.splitext(filename)[-1].lower()
                if ext not in INVOICE_EXTENSIONS:
                    continue

                tmp_dir = tempfile.mkdtemp(prefix="email_invoice_")
                safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
                file_path = os.path.join(tmp_dir, safe_name)
                with open(file_path, "wb") as f:
                    f.write(part.get_payload(decode=True))
                attachments.append({"name": safe_name, "path": file_path})

            if attachments:
                results.append({
                    "subject": subject,
                    "sender": sender,
                    "date": date,
                    "attachments": attachments,
                })

        mail.logout()
        return results, None

    except imaplib.IMAP4.error as e:
        err = str(e)
        if "AUTHENTICATIONFAILED" in err or "Invalid credentials" in err:
            domain = email_address.split("@")[-1].lower()
            if "gmail" in domain:
                return [], (
                    "Authentication failed. Gmail requires an App Password instead of your regular password. "
                    "Go to: Google Account → Security → 2-Step Verification → App Passwords → Generate one."
                )
            return [], "Authentication failed. Check your email and password."
        return [], f"IMAP error: {err}"
    except Exception as e:
        return [], f"Connection error: {str(e)}"
