"""
FastAPI backend — Invoice Processing Automation System.
Run: uvicorn api:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from dotenv import load_dotenv
load_dotenv(override=True)

from database import get_db, init_db
from models import EmailConfig, Invoice, InvoiceLineItem, ProcessingJob, User, Webhook, UserModelConfig
from destinations import route_approved_invoice
from invoice_processing_automation_system.tools.custom_tool import (
    PDFTextExtractor, ImageTextExtractor, extract_image_with_llava
)

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change-this-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 8

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

app = FastAPI(
    title="Invoice Processing Automation API",
    description="AI-powered invoice extraction, validation and routing",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()
    # Start background services
    from scheduler import start_scheduler
    from worker import start_worker
    start_scheduler(interval_seconds=30)   # check every 30s
    start_worker(poll_interval_seconds=5)  # pick up jobs every 5s


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _create_token(email: str) -> str:
    exp = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": email, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            raise exc
    except JWTError:
        raise exc
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise exc
    return user


# ── Auth endpoints ────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


@app.post("/auth/register", tags=["Auth"])
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=req.email, name=req.name, password_hash=_hash(req.password))
    db.add(user); db.commit()
    return {"message": "Registered successfully", "email": user.email}


@app.post("/auth/login", tags=["Auth"])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or user.password_hash != _hash(form.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user.last_login = datetime.utcnow()
    db.commit()
    return {"access_token": _create_token(user.email), "token_type": "bearer", "name": user.name}


@app.get("/auth/me", tags=["Auth"])
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "name": user.name}


# ── Email Config endpoints ────────────────────────────────────────────────────

class EmailConfigIn(BaseModel):
    email: str
    password: str                          # App password
    display_name: Optional[str] = None
    # Optional overrides — auto-detected from domain if not provided
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    imap_encryption: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_encryption: Optional[str] = None
    folder: str = "INBOX"
    poll_interval_minutes: int = 1   # poll every minute by default
    mark_as_read: bool = True
    delete_after_process: bool = False
    max_emails_per_poll: int = 50
    is_active: bool = True


# Known IMAP/SMTP settings by domain
_EMAIL_PRESETS = {
    "gmail.com":       {"imap_host": "imap.gmail.com",            "imap_port": 993, "imap_encryption": "SSL/TLS", "smtp_host": "smtp.gmail.com",           "smtp_port": 465, "smtp_encryption": "SSL/TLS"},
    "googlemail.com":  {"imap_host": "imap.gmail.com",            "imap_port": 993, "imap_encryption": "SSL/TLS", "smtp_host": "smtp.gmail.com",           "smtp_port": 465, "smtp_encryption": "SSL/TLS"},
    "outlook.com":     {"imap_host": "outlook.office365.com",     "imap_port": 993, "imap_encryption": "SSL/TLS", "smtp_host": "smtp.office365.com",       "smtp_port": 587, "smtp_encryption": "STARTTLS"},
    "hotmail.com":     {"imap_host": "outlook.office365.com",     "imap_port": 993, "imap_encryption": "SSL/TLS", "smtp_host": "smtp.office365.com",       "smtp_port": 587, "smtp_encryption": "STARTTLS"},
    "live.com":        {"imap_host": "outlook.office365.com",     "imap_port": 993, "imap_encryption": "SSL/TLS", "smtp_host": "smtp.office365.com",       "smtp_port": 587, "smtp_encryption": "STARTTLS"},
    "yahoo.com":       {"imap_host": "imap.mail.yahoo.com",       "imap_port": 993, "imap_encryption": "SSL/TLS", "smtp_host": "smtp.mail.yahoo.com",      "smtp_port": 465, "smtp_encryption": "SSL/TLS"},
    "yahoo.co.uk":     {"imap_host": "imap.mail.yahoo.com",       "imap_port": 993, "imap_encryption": "SSL/TLS", "smtp_host": "smtp.mail.yahoo.com",      "smtp_port": 465, "smtp_encryption": "SSL/TLS"},
    "icloud.com":      {"imap_host": "imap.mail.me.com",          "imap_port": 993, "imap_encryption": "SSL/TLS", "smtp_host": "smtp.mail.me.com",         "smtp_port": 587, "smtp_encryption": "STARTTLS"},
    "me.com":          {"imap_host": "imap.mail.me.com",          "imap_port": 993, "imap_encryption": "SSL/TLS", "smtp_host": "smtp.mail.me.com",         "smtp_port": 587, "smtp_encryption": "STARTTLS"},
}

def _resolve_email_config(email: str, data: EmailConfigIn) -> dict:
    """Fill in IMAP/SMTP settings from domain if not explicitly provided."""
    domain = email.split("@")[-1].lower()
    preset = _EMAIL_PRESETS.get(domain, {
        "imap_host": f"imap.{domain}", "imap_port": 993, "imap_encryption": "SSL/TLS",
        "smtp_host": f"smtp.{domain}", "smtp_port": 587, "smtp_encryption": "STARTTLS",
    })
    return {
        "email": email,
        "username": email,  # username = email for most providers
        "password": data.password,
        "display_name": data.display_name or email,
        "imap_host": data.imap_host or preset["imap_host"],
        "imap_port": data.imap_port or preset["imap_port"],
        "imap_encryption": data.imap_encryption or preset["imap_encryption"],
        "smtp_host": data.smtp_host or preset["smtp_host"],
        "smtp_port": data.smtp_port or preset["smtp_port"],
        "smtp_encryption": data.smtp_encryption or preset["smtp_encryption"],
        "folder": data.folder,
        "poll_interval_minutes": data.poll_interval_minutes,
        "mark_as_read": data.mark_as_read,
        "delete_after_process": data.delete_after_process,
        "max_emails_per_poll": data.max_emails_per_poll,
        "is_active": data.is_active,
    }


@app.get("/settings/email", tags=["Settings"])
def get_email_config(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cfg = db.query(EmailConfig).filter(EmailConfig.user_id == user.id).first()
    if not cfg:
        return None
    return {k: v for k, v in cfg.__dict__.items() if not k.startswith("_")}


@app.put("/settings/email", tags=["Settings"])
def save_email_config(data: EmailConfigIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    resolved = _resolve_email_config(data.email, data)
    cfg = db.query(EmailConfig).filter(EmailConfig.user_id == user.id).first()
    if cfg:
        # Don't overwrite password if empty
        if not resolved.get("password"):
            resolved.pop("password", None)
        for k, v in resolved.items():
            setattr(cfg, k, v)
    else:
        cfg = EmailConfig(user_id=user.id, **resolved)
        db.add(cfg)
    db.commit()
    return {"message": "Email config saved", "imap_host": cfg.imap_host, "imap_port": cfg.imap_port}


@app.post("/settings/email/poll-now", tags=["Settings"])
def poll_now(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Manually trigger email polling for this user right now."""
    from scheduler import poll_user_emails
    cfg = db.query(EmailConfig).filter(EmailConfig.user_id == user.id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="No email config found")
    count = poll_user_emails(cfg, db)
    return {"message": f"Polled successfully", "new_jobs_queued": count}


@app.post("/settings/email/test", tags=["Settings"])
def test_email_connection(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cfg = db.query(EmailConfig).filter(EmailConfig.user_id == user.id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="No email config found")
    try:
        import imaplib
        # Always test IMAP (incoming) — that's what the scheduler uses
        if cfg.imap_encryption in ("SSL/TLS", "SSL"):
            mail = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port)
        else:
            mail = imaplib.IMAP4(cfg.imap_host, cfg.imap_port)
            if cfg.imap_encryption == "STARTTLS":
                mail.starttls()
        mail.login(cfg.username, cfg.password)
        # Check the folder exists
        status, _ = mail.select(cfg.folder or "INBOX")
        mail.logout()
        if status == "OK":
            return {"success": True, "message": f"Connected to {cfg.imap_host}:{cfg.imap_port} successfully"}
        return {"success": False, "message": f"Connected but folder '{cfg.folder}' not found"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ── Webhook endpoints ─────────────────────────────────────────────────────────

class WebhookIn(BaseModel):
    name: str
    url: str
    method: str = "POST"
    auth_type: str = "None"
    auth_credentials: Optional[dict] = None
    content_type: str = "application/json"
    custom_headers: Optional[dict] = None
    payload_template: Optional[str] = None
    retry_enabled: bool = False
    retry_attempts: int = 3
    retry_delay_seconds: int = 30
    timeout_seconds: int = 30
    is_active: bool = True


@app.get("/settings/webhooks", tags=["Settings"])
def list_webhooks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hooks = db.query(Webhook).filter(Webhook.user_id == user.id).all()
    return [{k: v for k, v in h.__dict__.items() if not k.startswith("_")} for h in hooks]


@app.post("/settings/webhooks", tags=["Settings"])
def create_webhook(data: WebhookIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hook = Webhook(user_id=user.id, **data.model_dump())
    db.add(hook); db.commit()
    return {"id": hook.id, "message": "Webhook created"}


@app.put("/settings/webhooks/{webhook_id}", tags=["Settings"])
def update_webhook(webhook_id: str, data: WebhookIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hook = db.query(Webhook).filter(Webhook.id == webhook_id, Webhook.user_id == user.id).first()
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    for k, v in data.model_dump().items():
        setattr(hook, k, v)
    db.commit()
    return {"message": "Webhook updated"}


@app.delete("/settings/webhooks/{webhook_id}", tags=["Settings"])
def delete_webhook(webhook_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hook = db.query(Webhook).filter(Webhook.id == webhook_id, Webhook.user_id == user.id).first()
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    db.delete(hook); db.commit()
    return {"message": "Webhook deleted"}


@app.post("/settings/webhooks/{webhook_id}/test", tags=["Settings"])
def test_webhook(webhook_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hook = db.query(Webhook).filter(Webhook.id == webhook_id, Webhook.user_id == user.id).first()
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    import requests as req
    try:
        test_payload = {"test": True, "invoice_number": "TEST-001", "total_amount": 0, "status": "test"}
        r = req.post(hook.url, json=test_payload, timeout=hook.timeout_seconds)
        return {"success": True, "status_code": r.status_code, "response": r.text[:500]}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ── Model Config endpoints ────────────────────────────────────────────────────

class ModelConfigIn(BaseModel):
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@app.get("/settings/model", tags=["Settings"])
def get_model_config(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cfg = db.query(UserModelConfig).filter(UserModelConfig.user_id == user.id).first()
    default_model = os.environ.get("MODEL", "ollama/qwen3.5:9b")
    default_base_url = os.environ.get("OLLAMA_BASE_URL", "")
    if not cfg:
        return {"model_name": None, "api_key": None, "base_url": None,
                "effective_model": default_model, "effective_base_url": default_base_url}
    return {
        "model_name": cfg.model_name,
        "api_key": "***" if cfg.api_key else None,  # mask key
        "base_url": cfg.base_url,
        "effective_model": cfg.model_name or default_model,
        "effective_base_url": cfg.base_url or default_base_url,
    }


@app.put("/settings/model", tags=["Settings"])
def save_model_config(data: ModelConfigIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cfg = db.query(UserModelConfig).filter(UserModelConfig.user_id == user.id).first()
    if cfg:
        if data.model_name is not None: cfg.model_name = data.model_name or None
        if data.api_key is not None: cfg.api_key = data.api_key or None
        if data.base_url is not None: cfg.base_url = data.base_url or None
    else:
        cfg = UserModelConfig(user_id=user.id, model_name=data.model_name or None,
                              api_key=data.api_key or None, base_url=data.base_url or None)
        db.add(cfg)
    db.commit()
    return {"message": "Model config saved"}


@app.delete("/settings/model", tags=["Settings"])
def reset_model_config(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Reset to system defaults."""
    cfg = db.query(UserModelConfig).filter(UserModelConfig.user_id == user.id).first()
    if cfg:
        db.delete(cfg)
        db.commit()
    return {"message": "Reset to system defaults"}


# ── Invoice endpoints ─────────────────────────────────────────────────────────

def _invoice_to_dict(inv: Invoice) -> dict:
    d = {k: v for k, v in inv.__dict__.items() if not k.startswith("_")}
    d["line_items"] = [
        {k: v for k, v in li.__dict__.items() if not k.startswith("_")}
        for li in inv.line_items
    ]
    return d


@app.get("/invoices", tags=["Invoices"])
def list_invoices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invoices = db.query(Invoice).filter(Invoice.user_id == user.id).order_by(Invoice.created_at.desc()).all()
    return [_invoice_to_dict(i) for i in invoices]


@app.get("/invoices/{invoice_id}", tags=["Invoices"])
def get_invoice(invoice_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return _invoice_to_dict(inv)


class ApprovalRequest(BaseModel):
    reject_reason: Optional[str] = None


@app.patch("/invoices/{invoice_id}/approve", tags=["Invoices"])
def approve_invoice(invoice_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    inv.approval_status = "APPROVED"
    inv.approved_by = user.name
    inv.approved_at = datetime.utcnow()
    db.commit()

    # Route to all configured webhooks — detect Slack vs ERP by URL
    webhooks = db.query(Webhook).filter(Webhook.user_id == user.id, Webhook.is_active == True).all()
    erp_webhooks = []
    slack_urls = []
    notification_emails = []

    for w in webhooks:
        if "hooks.slack.com" in w.url or "slack.com/services" in w.url:
            slack_urls.append(w.url)
        else:
            # Pass full webhook config so auth/headers/template are applied
            erp_webhooks.append({
                "url": w.url,
                "method": w.method or "POST",
                "auth_type": w.auth_type or "None",
                "auth_credentials": w.auth_credentials or {},
                "content_type": w.content_type or "application/json",
                "custom_headers": w.custom_headers or {},
                "payload_template": w.payload_template,
                "timeout_seconds": w.timeout_seconds or 30,
            })

    # Get notification emails from user settings (stored in user_model_configs or a future settings table)
    # For now, check if any webhook URL looks like an email
    routing = route_approved_invoice(
        inv.full_json or {},
        {"erp_webhooks": erp_webhooks, "slack_webhooks": slack_urls, "notification_emails": notification_emails},
        approved_by=user.name,
    )
    return {"status": "approved", "routing": routing}


@app.patch("/invoices/{invoice_id}/reject", tags=["Invoices"])
def reject_invoice(invoice_id: str, body: ApprovalRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    inv.approval_status = "REJECTED"
    inv.approved_by = user.name
    inv.approved_at = datetime.utcnow()
    inv.rejected_reason = body.reject_reason or ""
    db.commit()
    return {"status": "rejected"}


# ── Manual invoice upload ─────────────────────────────────────────────────────

def _parse_json(text: str):
    if not text: return None
    try: return json.loads(text.strip())
    except: pass
    for pat in [r"```(?:json)?\s*(\{.*?\})\s*```", r"(\{[\s\S]*\})"]:
        m = re.search(pat, text, re.DOTALL)
        if m:
            try: return json.loads(m.group(1))
            except: pass
    return None


@app.post("/invoices/upload", tags=["Invoices"])
async def upload_invoice(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload invoice file — creates a queued job, worker processes it async."""
    upload_dir = tempfile.mkdtemp(prefix="invoices_")
    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    job = ProcessingJob(
        user_id=user.id,
        file_name=file.filename,
        file_path=file_path,
        source="upload",
        status="queued",
    )
    db.add(job); db.commit()
    return {"job_id": job.id, "status": "queued", "file_name": file.filename}


@app.get("/invoices/jobs/{job_id}", tags=["Invoices"])
def job_status(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id, ProcessingJob.user_id == user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    result = {k: v for k, v in job.__dict__.items() if not k.startswith("_")}
    # Include invoice data if done
    if job.status == "done" and job.invoice_id:
        inv = db.query(Invoice).filter(Invoice.id == job.invoice_id).first()
        if inv:
            result["invoice"] = _invoice_to_dict(inv)
    return result


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health(db: Session = Depends(get_db)):
    import requests as req
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://110.39.187.178:11434")
    model_ok = False
    try:
        r = req.get(f"{ollama_url}/api/tags", timeout=5)
        model_ok = r.status_code == 200
    except Exception:
        pass

    # DB check
    db_ok = False
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    return {
        "status": "ok" if (model_ok and db_ok) else "degraded",
        "model_reachable": model_ok,
        "database": "connected" if db_ok else "error",
        "active_model": os.environ.get("MODEL", "ollama/qwen3.5:9b"),
    }
