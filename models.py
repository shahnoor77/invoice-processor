"""
SQLAlchemy ORM models — one file, all tables.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


# ── Users ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    email_config: Mapped[Optional["EmailConfig"]] = relationship("EmailConfig", back_populates="user", uselist=False, cascade="all, delete-orphan")
    webhooks: Mapped[list["Webhook"]] = relationship("Webhook", back_populates="user", cascade="all, delete-orphan")
    invoices: Mapped[list["Invoice"]] = relationship("Invoice", back_populates="user", cascade="all, delete-orphan")
    jobs: Mapped[list["ProcessingJob"]] = relationship("ProcessingJob", back_populates="user", cascade="all, delete-orphan")


# ── Email Configuration ────────────────────────────────────────────────────────

class EmailConfig(Base):
    __tablename__ = "email_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, unique=True)

    # Identity
    display_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)  # store encrypted in prod

    # IMAP (incoming)
    imap_host: Mapped[str] = mapped_column(String, nullable=False)
    imap_port: Mapped[int] = mapped_column(Integer, default=993)
    imap_encryption: Mapped[str] = mapped_column(String, default="SSL/TLS")
    imap_auth: Mapped[str] = mapped_column(String, default="Normal Password")

    # SMTP (outgoing)
    smtp_host: Mapped[str] = mapped_column(String, nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, default=465)
    smtp_encryption: Mapped[str] = mapped_column(String, default="SSL/TLS")

    # Polling behaviour
    folder: Mapped[str] = mapped_column(String, default="INBOX")
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, default=5)
    mark_as_read: Mapped[bool] = mapped_column(Boolean, default=True)
    delete_after_process: Mapped[bool] = mapped_column(Boolean, default=False)
    max_emails_per_poll: Mapped[int] = mapped_column(Integer, default=50)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Tracking
    last_polled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="email_config")


# ── Webhooks ──────────────────────────────────────────────────────────────────

class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)

    name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    method: Mapped[str] = mapped_column(String, default="POST")
    auth_type: Mapped[str] = mapped_column(String, default="None")
    auth_credentials: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # bearer/apikey/basic/hmac
    content_type: Mapped[str] = mapped_column(String, default="application/json")
    custom_headers: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    payload_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_attempts: Mapped[int] = mapped_column(Integer, default=3)
    retry_delay_seconds: Mapped[int] = mapped_column(Integer, default=30)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="webhooks")


# ── Invoices ──────────────────────────────────────────────────────────────────

class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)

    # Source
    file_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, default="upload")  # upload | email

    # Invoice fields
    invoice_number: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    invoice_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    due_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    payment_terms: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    purchase_order: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Sender (vendor)
    sender_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sender_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sender_city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sender_country: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sender_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sender_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sender_tax_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Receiver (bill-to)
    receiver_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    receiver_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    receiver_city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    receiver_country: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    receiver_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    receiver_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Financials
    currency: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subtotal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    discount_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tax_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tax_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    shipping: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    amount_paid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    amount_due: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Extra
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bank_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ocr_confidence: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    full_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Status
    approval_status: Mapped[str] = mapped_column(String, default="PENDING", index=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rejected_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="invoices")
    line_items: Mapped[list["InvoiceLineItem"]] = relationship("InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan")


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    invoice_id: Mapped[str] = mapped_column(String, ForeignKey("invoices.id"), nullable=False, index=True)

    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    unit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    discount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="line_items")


# ── Processing Jobs ───────────────────────────────────────────────────────────

class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)

    file_name: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # temp path
    source: Mapped[str] = mapped_column(String, default="upload")  # upload | email
    email_subject: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email_sender: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(String, default="queued", index=True)  # queued | processing | done | failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    invoice_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("invoices.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="jobs")
