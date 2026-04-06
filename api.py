"""
FastAPI backend for Invoice Processing Automation System.
Run: uvicorn api:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
import json
import os
import re
import sys
import tempfile
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from dotenv import load_dotenv
load_dotenv(override=True)

from auth import (
    User, UserSettings, authenticate_user, create_access_token,
    get_current_user, register_user, update_user_settings,
)
from jobs import create_job, get_job, list_jobs, run_in_background, update_job
from destinations import route_approved_invoice
from invoice_processing_automation_system.sheets import save_invoice, get_processed_invoices, update_approval_status
from invoice_processing_automation_system.tools.custom_tool import PDFTextExtractor, ImageTextExtractor, extract_image_with_llava

app = FastAPI(
    title="Invoice Processing Automation API",
    description="AI-powered invoice extraction, validation and routing",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


@app.post("/auth/register", tags=["Auth"])
def register(req: RegisterRequest):
    user = register_user(req.email, req.password, req.name)
    return {"message": "Registered successfully", "email": user.email}


@app.post("/auth/login", tags=["Auth"])
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form.username, form.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer", "name": user.name}


@app.get("/auth/me", tags=["Auth"])
def me(user: User = Depends(get_current_user)):
    return user


# ── Settings ──────────────────────────────────────────────────────────────────

@app.get("/settings", tags=["Settings"])
def get_settings(user: User = Depends(get_current_user)):
    return user.settings


@app.put("/settings", tags=["Settings"])
def save_settings(settings: UserSettings, user: User = Depends(get_current_user)):
    update_user_settings(user.email, settings)
    return {"message": "Settings saved"}


# ── Invoice Processing ────────────────────────────────────────────────────────

def _extract_ocr(file_path: str, ollama_url: str) -> str:
    ext = os.path.splitext(file_path)[-1].lower()
    if ext == ".pdf":
        return PDFTextExtractor()._run(file_path)
    result = extract_image_with_llava(file_path, ollama_url)
    if result.startswith("Error"):
        result = ImageTextExtractor()._run(file_path)
    return result


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


def _run_crew(job_id: str, file_path: str, file_name: str, user_email: str, erp_system: str, notification_channel: str):
    """Background task — runs OCR + crew, saves result to job store."""
    update_job(job_id, status="processing")
    try:
        from invoice_processing_automation_system.crew import InvoiceProcessingAutomationSystemCrew

        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://110.39.187.178:11434")
        ocr_text = _extract_ocr(file_path, ollama_url)
        intake_source = f"Files to process:\n{file_path}"

        result = InvoiceProcessingAutomationSystemCrew().crew().kickoff(inputs={
            "intake_source": intake_source,
            "ocr_text": ocr_text,
            "erp_system": erp_system,
            "notification_channel": notification_channel,
        })

        extracted_json = None
        for task_output in (result.tasks_output or []):
            if hasattr(task_output, "name") and task_output.name == "structured_data_extraction":
                extracted_json = _parse_json(task_output.raw)
                break

        if not extracted_json:
            extracted_json = _parse_json(str(result.raw))

        # Auto-save to sheets as PENDING with user email
        sheet_id = os.environ.get("GOOGLE_SHEET_ID")
        if sheet_id and extracted_json:
            save_invoice(extracted_json, file_name, "PENDING", user_email)

        update_job(job_id, status="done", result=extracted_json,
                   completed_at=__import__("datetime").datetime.utcnow().isoformat())
    except Exception as e:
        update_job(job_id, status="failed", error=str(e),
                   completed_at=__import__("datetime").datetime.utcnow().isoformat())


@app.post("/invoices/process", tags=["Invoices"])
async def process_invoice(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    erp_system: str = Form(default=""),
    notification_channel: str = Form(default=""),
    user: User = Depends(get_current_user),
):
    """Upload an invoice file and start async processing. Returns job_id to poll."""
    upload_dir = tempfile.mkdtemp(prefix="invoices_")
    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    job_id = create_job(user.email, file.filename)
    background_tasks.add_task(
        _run_crew, job_id, file_path, file.filename,
        user.email, erp_system, notification_channel,
    )
    return {"job_id": job_id, "status": "processing", "file_name": file.filename}


@app.get("/invoices/status/{job_id}", tags=["Invoices"])
def job_status(job_id: str, user: User = Depends(get_current_user)):
    """Poll processing status. status: queued | processing | done | failed"""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["user_email"] != user.email:
        raise HTTPException(status_code=403, detail="Not your job")
    return job


@app.get("/invoices/jobs", tags=["Invoices"])
def my_jobs(user: User = Depends(get_current_user)):
    """List all processing jobs for the current user."""
    return list_jobs(user.email)


@app.get("/invoices", tags=["Invoices"])
def list_invoices(user: User = Depends(get_current_user)):
    """List invoices for the current user only."""
    records = get_processed_invoices(user_email=user.email)
    # Fallback: if no records found for this user, return all (handles migration from Streamlit)
    if not records:
        records = get_processed_invoices(user_email="")
    return records


class ApprovalRequest(BaseModel):
    row_number: int
    invoice_data: dict
    reject_reason: Optional[str] = None


@app.patch("/invoices/{row_number}/approve", tags=["Invoices"])
def approve_invoice(row_number: int, body: ApprovalRequest, user: User = Depends(get_current_user)):
    """Approve invoice — updates sheet status and routes to configured destinations."""
    ok, err = update_approval_status(row_number, "APPROVED")
    if not ok:
        raise HTTPException(status_code=500, detail=f"Sheet update failed: {err}")

    # Get fresh user settings
    from auth import get_user
    fresh_user = get_user(user.email)
    settings = fresh_user.settings.model_dump() if fresh_user else {}

    routing_results = route_approved_invoice(body.invoice_data, settings)
    return {"status": "approved", "routing": routing_results}


@app.patch("/invoices/{row_number}/reject", tags=["Invoices"])
def reject_invoice(row_number: int, body: ApprovalRequest, user: User = Depends(get_current_user)):
    """Reject invoice — updates sheet status."""
    reason = body.reject_reason or "No reason provided"
    ok, err = update_approval_status(row_number, f"REJECTED: {reason}")
    if not ok:
        raise HTTPException(status_code=500, detail=f"Sheet update failed: {err}")
    return {"status": "rejected", "reason": reason}


# ── Email Fetching ────────────────────────────────────────────────────────────

class EmailFetchRequest(BaseModel):
    email: str
    password: str                          # App password for Gmail, regular for others
    max_emails: int = 10
    unread_only: bool = True
    from_filter: Optional[str] = None     # filter by sender e.g. vendor@acme.com
    subject_filter: Optional[str] = None  # filter by subject keyword e.g. "invoice"
    since_date: Optional[str] = None      # filter since date e.g. "01-Jan-2024"


@app.post("/email/fetch", tags=["Email"])
def fetch_emails(req: EmailFetchRequest, user: User = Depends(get_current_user)):
    """
    Fetch emails with invoice attachments via IMAP.
    Gmail requires an App Password. Outlook/Yahoo/corporate use regular password.
    Returns list of emails with attachment file paths ready for processing.
    """
    from invoice_processing_automation_system.email_fetcher import fetch_invoice_emails
    emails, error = fetch_invoice_emails(
        email_address=req.email,
        password=req.password,
        max_emails=req.max_emails,
        unread_only=req.unread_only,
        from_filter=req.from_filter or "",
        subject_filter=req.subject_filter or "",
        since_date=req.since_date or "",
    )
    if error:
        raise HTTPException(status_code=400, detail=error)

    # Return email list with attachment info (paths are temp, use immediately)
    return {
        "count": len(emails),
        "emails": [
            {
                "subject": e["subject"],
                "sender": e["sender"],
                "date": e["date"],
                "attachments": [
                    {"name": a["name"], "path": a["path"]}
                    for a in e["attachments"]
                ],
            }
            for e in emails
        ],
    }


@app.post("/email/process-attachment", tags=["Email"])
async def process_email_attachment(
    background_tasks: BackgroundTasks,
    file_path: str = Form(...),
    file_name: str = Form(...),
    erp_system: str = Form(default=""),
    notification_channel: str = Form(default=""),
    user: User = Depends(get_current_user),
):
    """
    Process a specific attachment fetched from email.
    Use the file_path returned by /email/fetch.
    """
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Attachment file not found. Fetch emails again.")

    job_id = create_job(user.email, file_name)
    background_tasks.add_task(
        _run_crew, job_id, file_path, file_name,
        user.email, erp_system, notification_channel,
    )
    return {"job_id": job_id, "status": "processing", "file_name": file_name}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    """Check model and sheets connectivity."""
    import requests as req
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://110.39.187.178:11434")
    model_ok = False
    try:
        r = req.get(f"{ollama_url}/api/tags", timeout=5)
        model_ok = r.status_code == 200
    except Exception:
        pass

    sheets_ok = bool(os.environ.get("GOOGLE_SHEET_ID") and os.environ.get("GOOGLE_CREDENTIALS_FILE"))

    return {
        "status": "ok" if model_ok else "degraded",
        "model_reachable": model_ok,
        "ollama_url": ollama_url,
        "active_model": os.environ.get("MODEL", "ollama/qwen3.5:9b"),
        "sheets_configured": sheets_ok,
    }
