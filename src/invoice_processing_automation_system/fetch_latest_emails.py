import os
import base64
import logging
import mimetypes
import tempfile
from typing import List, Dict, Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
DOWNLOAD_DIR = "downloaded_attachments"
LOG_FILE = "gmail_fetch.log"
DEFAULT_QUERY = "in:inbox is:unread"


# -----------------------------
# Logging setup
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)


# -----------------------------
# Gmail auth / service
# -----------------------------
def get_gmail_service():
    if not os.path.exists("token.json"):
        raise FileNotFoundError("token.json not found. Run your auth script first.")

    creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open("token.json", "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        else:
            raise RuntimeError("Token is invalid. Re-run auth setup.")

    return build("gmail", "v1", credentials=creds)


# -----------------------------
# Helpers
# -----------------------------
def sanitize_filename(filename: str) -> str:
    invalid_chars = '<>:"/\\|?*'
    for ch in invalid_chars:
        filename = filename.replace(ch, "_")
    return filename.strip() or "attachment"


def ensure_unique_filepath(filepath: str) -> str:
    if not os.path.exists(filepath):
        return filepath

    base, ext = os.path.splitext(filepath)
    counter = 1
    while True:
        new_path = f"{base}_{counter}{ext}"
        if not os.path.exists(new_path):
            return new_path
        counter += 1


def decode_base64url(data: str) -> bytes:
    return base64.urlsafe_b64decode(data.encode("UTF-8"))


def is_invoice_filename(filename: str) -> bool:
    return "invoice" in filename.lower()


# -----------------------------
# Attachment handling
# -----------------------------
def collect_attachments(
    parts: List[Dict[str, Any]],
    found: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    if found is None:
        found = []

    for part in parts:
        filename = part.get("filename", "")
        body = part.get("body", {})
        attachment_id = body.get("attachmentId")
        mime_type = part.get("mimeType", "")
        nested_parts = part.get("parts", [])

        if filename and attachment_id:
            found.append({
                "filename": filename,
                "attachment_id": attachment_id,
                "mime_type": mime_type,
            })

        if nested_parts:
            collect_attachments(nested_parts, found)

    return found


def save_attachment(service, msg_id: str, attachment_meta: Dict[str, Any], save_dir: str) -> str:
    attachment = service.users().messages().attachments().get(
        userId="me",
        messageId=msg_id,
        id=attachment_meta["attachment_id"]
    ).execute()

    file_data = attachment.get("data")
    if not file_data:
        raise ValueError(f"No data found for attachment: {attachment_meta['filename']}")

    file_bytes = decode_base64url(file_data)
    filename = sanitize_filename(attachment_meta["filename"])

    # Add extension if missing
    if "." not in filename:
        guessed_ext = mimetypes.guess_extension(attachment_meta.get("mime_type", ""))
        if guessed_ext:
            filename += guessed_ext

    os.makedirs(save_dir, exist_ok=True)
    filepath = ensure_unique_filepath(os.path.join(save_dir, filename))

    with open(filepath, "wb") as f:
        f.write(file_bytes)

    return filepath


# -----------------------------
# Main fetch function
# -----------------------------
def fetch_latest_invoice_attachments(
    max_results: int = 5,
    query: Optional[str] = DEFAULT_QUERY,
    save_dir: Optional[str] = None
) -> List[str]:
    if save_dir is None:
        save_dir = tempfile.mkdtemp(prefix="invoices_")
        
    service = get_gmail_service()

    response = service.users().messages().list(
        userId="me",
        maxResults=max_results,
        q=query
    ).execute()

    messages = response.get("messages", [])
    saved_file_paths: List[str] = []

    if not messages:
        logging.info("No emails found.")
        return saved_file_paths

    for msg in messages:
        try:
            full_msg = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="full"
            ).execute()

            payload = full_msg.get("payload", {})
            parts = payload.get("parts", [])

            if not parts:
                continue

            attachments = collect_attachments(parts)

            for attachment_meta in attachments:
                filename = attachment_meta.get("filename", "")

                # Only process invoice files
                if not is_invoice_filename(filename):
                    logging.info(f"Skipping non-invoice: {filename}")
                    continue

                try:
                    filepath = save_attachment(
                        service=service,
                        msg_id=full_msg["id"],
                        attachment_meta=attachment_meta,
                        save_dir=save_dir
                    )
                    saved_file_paths.append(filepath)
                    logging.info(f"Saved invoice: {filepath}")
                except Exception as e:
                    logging.error(f"Failed to save {filename}: {e}")

        except Exception as e:
            logging.error(f"Failed to process message {msg.get('id')}: {e}")

    return saved_file_paths


# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    file_paths = fetch_latest_invoice_attachments()

    if not file_paths:
        print("No invoice attachments found.")
    else:
        print("Saved invoice files:")
        for path in file_paths:
            print(path)