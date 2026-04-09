"""
Database Setup & Management Script
===================================
Run this script to set up, migrate, or manage the database.

Usage:
    python db_setup.py setup       — Create database and all tables (first-time setup)
    python db_setup.py migrate     — Add any missing columns to existing tables
    python db_setup.py status      — Show table info and row counts
    python db_setup.py reset       — Drop all tables and recreate (WARNING: deletes all data)
    python db_setup.py create-db   — Create the PostgreSQL database itself (if it doesn't exist)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from dotenv import load_dotenv
load_dotenv(override=True)


def get_engine():
    from database import engine
    return engine


def cmd_setup():
    """Create all tables. Safe to run multiple times — won't overwrite existing data."""
    print("Setting up database tables...")
    from database import init_db
    init_db()
    print("✅ All tables created successfully.")
    cmd_status()


def cmd_migrate():
    """Add any missing columns to existing tables (non-destructive)."""
    from sqlalchemy import text, inspect
    engine = get_engine()
    inspector = inspect(engine)

    migrations = {
        "processing_jobs": [
            ("retry_count", "INTEGER DEFAULT 0"),
            ("email_message_id", "VARCHAR"),
        ],
        "invoices": [
            ("delivery_date", "VARCHAR"),
            ("payment_method", "VARCHAR"),
            ("reference", "VARCHAR"),
            ("sender_state", "VARCHAR"),
            ("sender_zip", "VARCHAR"),
            ("sender_website", "VARCHAR"),
            ("sender_vat_number", "VARCHAR"),
            ("sender_registration", "VARCHAR"),
            ("sender_bank_name", "VARCHAR"),
            ("sender_bank_account_holder", "VARCHAR"),
            ("sender_bank_account_number", "VARCHAR"),
            ("sender_bank_iban", "VARCHAR"),
            ("sender_bank_swift", "VARCHAR"),
            ("sender_bank_routing", "VARCHAR"),
            ("sender_bank_sort_code", "VARCHAR"),
            ("sender_bank_branch", "VARCHAR"),
            ("sender_bank_address", "VARCHAR"),
            ("receiver_state", "VARCHAR"),
            ("receiver_zip", "VARCHAR"),
            ("receiver_tax_id", "VARCHAR"),
            ("receiver_vat_number", "VARCHAR"),
            ("receiver_bank_name", "VARCHAR"),
            ("receiver_bank_account_holder", "VARCHAR"),
            ("receiver_bank_account_number", "VARCHAR"),
            ("receiver_bank_iban", "VARCHAR"),
            ("receiver_bank_swift", "VARCHAR"),
            ("receiver_bank_routing", "VARCHAR"),
            ("receiver_bank_sort_code", "VARCHAR"),
            ("receiver_bank_branch", "VARCHAR"),
            ("exchange_rate", "FLOAT"),
            ("discount_percent", "FLOAT"),
            ("tax_type", "VARCHAR"),
            ("handling", "FLOAT"),
            ("other_charges", "FLOAT"),
            ("deposit", "FLOAT"),
            ("terms_and_conditions", "TEXT"),
            # Columns that may have been removed from old schema
            ("bank_details", "TEXT"),  # kept for backward compat
        ],
        "user_model_configs": [],
    }

    added = 0
    skipped = 0

    with engine.connect() as conn:
        for table, columns in migrations.items():
            # Check if table exists
            existing_tables = inspector.get_table_names()
            if table not in existing_tables:
                print(f"  ⚠️  Table '{table}' does not exist — run 'setup' first")
                continue

            existing_cols = {col["name"] for col in inspector.get_columns(table)}

            for col_name, col_type in columns:
                if col_name not in existing_cols:
                    try:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                        print(f"  ✅ Added column: {table}.{col_name}")
                        added += 1
                    except Exception as e:
                        print(f"  ❌ Failed to add {table}.{col_name}: {e}")
                else:
                    skipped += 1

        conn.commit()

    # Also run init_db to create any new tables
    from database import init_db
    init_db()

    print(f"\nMigration complete: {added} column(s) added, {skipped} already existed.")


def cmd_status():
    """Show database connection info, tables, and row counts."""
    from sqlalchemy import text, inspect
    engine = get_engine()

    db_url = os.environ.get("DATABASE_URL", "sqlite:///./invoice_dev.db")
    # Mask password in URL for display
    display_url = db_url
    if "@" in db_url:
        parts = db_url.split("@")
        creds = parts[0].split("://")[1]
        if ":" in creds:
            user = creds.split(":")[0]
            display_url = db_url.replace(creds, f"{user}:***")

    print(f"\n{'='*50}")
    print(f"Database: {display_url}")
    print(f"{'='*50}")

    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        if not tables:
            print("No tables found. Run: python db_setup.py setup")
            return

        with engine.connect() as conn:
            for table in sorted(tables):
                try:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.scalar()
                    cols = len(inspector.get_columns(table))
                    print(f"  📋 {table:<30} {count:>6} rows  ({cols} columns)")
                except Exception as e:
                    print(f"  ❌ {table}: {e}")

        print(f"\n✅ Database connection OK")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\nCheck your DATABASE_URL in .env")


def cmd_reset():
    """Drop all tables and recreate. WARNING: deletes all data."""
    confirm = input("\n⚠️  WARNING: This will DELETE ALL DATA. Type 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("Cancelled.")
        return

    from database import Base, engine, init_db
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("Recreating tables...")
    init_db()
    print("✅ Database reset complete.")


def cmd_create_db():
    """Create the PostgreSQL database if it doesn't exist."""
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url or "postgresql" not in db_url:
        print("This command only works with PostgreSQL.")
        print("Set DATABASE_URL=postgresql://user:password@host:5432/dbname in .env")
        return

    # Parse the URL to get database name and connect to postgres default db
    from urllib.parse import urlparse
    parsed = urlparse(db_url)
    db_name = parsed.path.lstrip("/")
    base_url = db_url.replace(f"/{db_name}", "/postgres")

    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(base_url, isolation_level="AUTOCOMMIT")
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'"))
            exists = result.fetchone()
            if exists:
                print(f"✅ Database '{db_name}' already exists.")
            else:
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                print(f"✅ Database '{db_name}' created successfully.")
        engine.dispose()
    except Exception as e:
        print(f"❌ Failed to create database: {e}")
        print("\nMake sure PostgreSQL is running and your credentials are correct.")


def cmd_help():
    print(__doc__)


COMMANDS = {
    "setup": cmd_setup,
    "migrate": cmd_migrate,
    "status": cmd_status,
    "reset": cmd_reset,
    "create-db": cmd_create_db,
    "help": cmd_help,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd in COMMANDS:
        COMMANDS[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(COMMANDS.keys())}")
        sys.exit(1)
