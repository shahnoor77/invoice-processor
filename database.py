"""
Database setup — SQLAlchemy with PostgreSQL.
Switch between SQLite (dev) and PostgreSQL (prod) via DATABASE_URL in .env.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///./invoice_dev.db"  # fallback to SQLite for dev without PostgreSQL
)

# PostgreSQL needs pool settings; SQLite doesn't support them
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Call once on startup."""
    from models import User, EmailConfig, Webhook, Invoice, InvoiceLineItem, ProcessingJob  # noqa
    Base.metadata.create_all(bind=engine)
