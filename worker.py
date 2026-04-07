"""
Invoice Processing Worker — picks up queued jobs and runs the AI crew.
Saves extracted invoice data to the DB with status PENDING.

Runs as a background thread alongside the API server.
"""
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from threading import Thread

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from dotenv import load_dotenv
load_dotenv(override=True)

from database import SessionLocal
from models import Invoice, InvoiceLineItem, ProcessingJob

logging.basicConfig(level=logging.INFO, format="%(asctime)s [WORKER] %(message)s")
log = logging.getLogger("worker")

_running = False


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


def _extract_ocr(file_path: str) -> str:
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


def _run_crew(ocr_text: str, file_path: str) -> dict | None:
    from invoice_processing_automation_system.crew import InvoiceProcessingAutomationSystemCrew
    result = InvoiceProcessingAutomationSystemCrew().crew().kickoff(inputs={
        "intake_source": f"Files to process:\n{file_path}",
        "ocr_text": ocr_text,
        "erp_system": "pending_approval",
        "notification_channel": "none",
    })
    # Extract JSON from structured_data_extraction task
    for task_output in (result.tasks_output or []):
        if hasattr(task_output, "name") and task_output.name == "structured_data_extraction":
            return _parse_json(task_output.raw)
    return _parse_json(str(result.raw))


def save_invoice_to_db(db, user_id: str, extracted: dict, file_name: str, source: str) -> Invoice:
    """Save extracted invoice JSON to the invoices table."""
    s = extracted.get("sender") or {}
    r = extracted.get("receiver") or {}

    invoice = Invoice(
        user_id=user_id,
        file_name=file_name,
        source=source,
        invoice_number=extracted.get("invoice_number"),
        invoice_date=extracted.get("invoice_date"),
        due_date=extracted.get("due_date"),
        payment_terms=extracted.get("payment_terms"),
        purchase_order=extracted.get("purchase_order"),
        sender_name=s.get("name"),
        sender_address=s.get("address"),
        sender_city=s.get("city"),
        sender_country=s.get("country"),
        sender_email=s.get("email"),
        sender_phone=s.get("phone"),
        sender_tax_id=s.get("tax_id"),
        receiver_name=r.get("name"),
        receiver_address=r.get("address"),
        receiver_city=r.get("city"),
        receiver_country=r.get("country"),
        receiver_email=r.get("email"),
        receiver_phone=r.get("phone"),
        currency=extracted.get("currency"),
        subtotal=_safe_float(extracted.get("subtotal")),
        discount_total=_safe_float(extracted.get("discount_total")),
        tax_rate=_safe_float(extracted.get("tax_rate")),
        tax_amount=_safe_float(extracted.get("tax_amount")),
        shipping=_safe_float(extracted.get("shipping")),
        total_amount=_safe_float(extracted.get("total_amount")),
        amount_paid=_safe_float(extracted.get("amount_paid")),
        amount_due=_safe_float(extracted.get("amount_due")),
        notes=extracted.get("notes"),
        bank_details=extracted.get("bank_details"),
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
    """Process a single queued job. Returns True on success."""
    log.info(f"Processing job {job.id}: {job.file_name} for user {job.user_id}")

    job.status = "processing"
    job.started_at = datetime.utcnow()
    db.commit()

    try:
        if not job.file_path or not os.path.exists(job.file_path):
            raise FileNotFoundError(f"File not found: {job.file_path}")

        # OCR
        ocr_text = _extract_ocr(job.file_path)

        # AI crew
        extracted = _run_crew(ocr_text, job.file_path)
        if not extracted:
            raise ValueError("AI crew returned no structured data")

        # Save to DB
        invoice = save_invoice_to_db(db, job.user_id, extracted, job.file_name, job.source)

        job.status = "done"
        job.invoice_id = invoice.id
        job.completed_at = datetime.utcnow()
        db.commit()

        log.info(f"Job {job.id} done → Invoice {invoice.id} (PENDING)")
        return True

    except Exception as e:
        log.error(f"Job {job.id} failed: {e}")
        job.status = "failed"
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()
        return False


def run_worker_cycle():
    """Pick up one queued job and process it."""
    db = SessionLocal()
    try:
        job = db.query(ProcessingJob).filter(
            ProcessingJob.status == "queued"
        ).order_by(ProcessingJob.created_at).first()

        if job:
            process_job(job, db)
    finally:
        db.close()


def worker_loop(poll_interval_seconds: int = 10):
    """Main loop — checks for queued jobs every N seconds."""
    global _running
    _running = True
    log.info("Invoice worker started")
    while _running:
        try:
            run_worker_cycle()
        except Exception as e:
            log.error(f"Worker cycle error: {e}")
        time.sleep(poll_interval_seconds)
    log.info("Invoice worker stopped")


def start_worker(poll_interval_seconds: int = 10) -> Thread:
    """Start worker in a background thread."""
    t = Thread(target=worker_loop, args=(poll_interval_seconds,), daemon=True, name="invoice-worker")
    t.start()
    return t


def stop_worker():
    global _running
    _running = False


if __name__ == "__main__":
    worker_loop()
