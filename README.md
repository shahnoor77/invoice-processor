# Automatic Invoice Processor

An AI-powered invoice processing system that automatically fetches invoices from email, extracts structured data using OCR and LLM agents, stores them in PostgreSQL, and routes approved invoices to ERP systems, Slack, or email.

---

## How It Works

```
Email Inbox (IMAP — any provider)
      ↓ scheduler.py polls every 1 min per user (parallel threads)
PostgreSQL DB → processing_jobs (status: queued)
      ↓ worker.py picks up jobs (parallel OCR + per-user AI lock)
OCR (Tesseract / LLaVA vision) → AI Crew (5 agents)
      ↓ Extracts: sender, receiver, bank details, line items, financials
PostgreSQL DB → invoices (status: PENDING)
      ↓ User reviews in UI → Approve / Reject
Destinations (parallel): ERP Webhook + Slack + Email
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI Engine | CrewAI — 5 agents (intake, extraction, validation, ERP, notification) |
| OCR | Tesseract (images) + pdfplumber (PDFs) + LLaVA vision model |
| LLM | Ollama (offline) or any cloud model via LiteLLM |
| Backend | FastAPI + PostgreSQL (SQLAlchemy) |
| Frontend | React + TypeScript + Tailwind + shadcn/ui |
| Email | IMAP polling — auto-detects provider settings |
| Threading | Parallel email polling, parallel OCR, parallel destination routing |

---

## Project Structure

```
├── api.py                  # FastAPI REST API — all endpoints
├── auth.py                 # JWT authentication
├── database.py             # SQLAlchemy engine + session factory
├── models.py               # DB models: users, invoices, webhooks, jobs, email_configs
├── scheduler.py            # Email poller — runs every 30s, polls per user in parallel
├── worker.py               # Invoice processor — parallel OCR, per-user AI lock, retry logic
├── destinations.py         # Routes approved invoices to ERP/Slack/email in parallel
├── db_setup.py             # Database management script
├── jobs.py                 # Legacy job queue (kept for compatibility)
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
├── Dockerfile              # Multi-stage: React build + Python backend
├── docker-compose.yml      # Full stack: API + PostgreSQL + nginx
├── nginx.conf              # Reverse proxy: serves React + proxies /api/* to FastAPI
├── invoiceiq-dash/         # React frontend (TypeScript + Tailwind + shadcn/ui)
│   ├── src/
│   │   ├── pages/          # Login, Invoices, InvoiceDetail, Settings
│   │   ├── components/     # UI components, settings forms
│   │   ├── lib/api.ts      # All API calls
│   │   └── context/        # Auth context
│   └── vite.config.ts
└── src/invoice_processing_automation_system/
    ├── crew.py             # CrewAI agents and tasks
    ├── config/
    │   ├── agents.yaml
    │   └── tasks.yaml      # Comprehensive extraction prompt
    └── tools/
        └── custom_tool.py  # PDFTextExtractor, ImageTextExtractor, LLaVA
```

---

## Local Setup (Development)

### Requirements
- Python 3.10–3.13 + [uv](https://docs.astral.sh/uv/)
- PostgreSQL 14+ (or Docker)
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (Windows) or `apt install tesseract-ocr` (Linux)
- Node.js 18+
- Ollama server or cloud model API key

### 1. Clone and install

```bash
git clone https://github.com/shahnoor77/invoice-processor.git
cd invoice-processor
pip install uv
uv sync
```

### 2. Create database

```bash
# Option A — script creates it
python db_setup.py create-db

# Option B — manually in pgAdmin
# CREATE DATABASE invoice_db;
```

### 3. Set up tables

```bash
python db_setup.py setup
```

### 4. Configure environment

```bash
cp .env.example .env
```

Key variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | `postgresql://postgres:password@localhost:5432/invoice_db` |
| `MODEL` | LLM to use (see options below) |
| `OLLAMA_BASE_URL` | Your Ollama server URL |
| `MODEL_API_KEY` | API key for cloud models |
| `JWT_SECRET_KEY` | Random secret for JWT tokens |
| `SMTP_USER` | Gmail for email notifications |
| `SMTP_PASSWORD` | Gmail App Password |
| `GOOGLE_SHEET_ID` | Optional Google Sheets export |

### 5. Run the API

```bash
uv run uvicorn api:app --host 0.0.0.0 --port 8000 --reload --reload-exclude ".venv"
```

Tables auto-create on first startup. API docs: `http://localhost:8000/docs`

### 6. Run the frontend

```bash
cd invoiceiq-dash
npm install
npm run dev
```

Open `http://localhost:8080`

---

## Switching LLM Models

Change `MODEL` in `.env`:

```bash
MODEL=ollama/qwen3.5:9b              # offline, recommended
MODEL=ollama/llama3.1:8b             # offline, faster
MODEL=groq/llama-3.3-70b-versatile   # Groq free tier
MODEL=gemini/gemini-2.0-flash        # Google free tier
MODEL=openai/gpt-4o-mini             # OpenAI
```

Users can also set their own model in Settings → AI Model (stored per-user in DB).

---

## Database Management

```bash
python db_setup.py setup       # First-time: create all tables
python db_setup.py migrate     # Add missing columns (run after pulling new code)
python db_setup.py status      # Show tables and row counts
python db_setup.py create-db   # Create the PostgreSQL database
python db_setup.py reset       # Drop and recreate all tables (deletes data!)
```

Always run `migrate` after pulling updates that add new DB columns.

---

## Docker (Production)

nginx serves the React frontend on port 80 and proxies `/api/*` to FastAPI — one URL for everything, no CORS issues.

```bash
cp .env.example .env
# Fill in your values

docker compose up --build
```

- App: `http://localhost` (port 80)
- API docs: `http://localhost/docs`
- PostgreSQL: port 5432

For Ollama VM access from Docker, the VM must bind to `0.0.0.0:11434`:
```bash
sudo systemctl edit ollama
# Add: Environment="OLLAMA_HOST=0.0.0.0:11434"
sudo systemctl restart ollama
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Create account |
| POST | `/auth/login` | Login, get JWT |
| GET | `/invoices` | List user's invoices |
| GET | `/invoices/{id}` | Full invoice with bank details + financials |
| POST | `/invoices/upload` | Upload invoice file → queued job |
| GET | `/invoices/jobs/{id}` | Poll job status |
| PATCH | `/invoices/{id}/approve` | Approve → routes to all destinations |
| PATCH | `/invoices/{id}/reject` | Reject with reason |
| GET | `/settings/email` | Get email config |
| PUT | `/settings/email` | Save email config (auto-detects IMAP/SMTP) |
| POST | `/settings/email/test` | Test IMAP connection |
| POST | `/settings/email/poll-now` | Trigger immediate email poll |
| GET | `/settings/webhooks` | List webhooks |
| POST | `/settings/webhooks` | Create webhook (with auth, headers, template) |
| PUT | `/settings/webhooks/{id}` | Update webhook |
| DELETE | `/settings/webhooks/{id}` | Delete webhook |
| POST | `/settings/webhooks/{id}/test` | Test webhook |
| GET | `/settings/model` | Get per-user model config |
| PUT | `/settings/model` | Set custom model/API key |
| GET | `/health` | System health check |

---

## Webhook Payload

Every approved invoice sends this structured JSON to configured ERP webhooks:

```json
{
  "event": "invoice.approved",
  "timestamp": "2026-04-09T14:30:00Z",
  "approved_by": "User Name",
  "invoice": { "invoice_number": "INV-001", "invoice_date": "...", "due_date": "..." },
  "sender": {
    "name": "Vendor Name", "address": "...", "tax_id": "...",
    "bank": { "bank_name": "...", "iban": "...", "swift_bic": "...", "account_number": "..." }
  },
  "receiver": {
    "name": "Client Name", "address": "...",
    "bank": {}
  },
  "line_items": [{ "description": "...", "quantity": 1, "unit_price": 500, "total": 500 }],
  "financials": {
    "currency": "USD", "subtotal": 500, "tax_rate": 8, "tax_amount": 40,
    "discount_total": 0, "shipping": 0, "total_amount": 540, "amount_due": 540
  },
  "notes": "..."
}
```

Slack gets a formatted message. Email gets a full HTML invoice with all details.

---

## For Team Members

1. Clone the repo
2. Install PostgreSQL locally, create `invoice_db`
3. Copy `.env.example` → `.env`, fill in your values
4. Get `google_credentials.json` from project owner (not in repo)
5. Install Tesseract OCR
6. Run `uv sync` then `python db_setup.py setup`
7. Run `uv run uvicorn api:app --host 0.0.0.0 --port 8000 --reload --reload-exclude ".venv"`
8. In another terminal: `cd invoiceiq-dash && npm install && npm run dev`

---

## Known Limitations

- Auth is JWT only — no OAuth, no password reset
- Users are in-memory on restart unless DB-backed (TODO: migrate auth to DB)
- OCR accuracy depends on image quality — use GPT-4o vision for near-perfect extraction
- Webhook retry on failure is logged but not automatically retried (TODO)
- No duplicate invoice detection across different email subjects
