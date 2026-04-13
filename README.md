# InvoiceIQ — AI-Powered Invoice Processing System

An AI-powered invoice processing system that automatically fetches invoices from email, extracts structured data using OCR and LLM agents, validates calculations, stores them in PostgreSQL, and routes approved invoices to ERP systems via webhooks.

---

## How It Works

```
Email Inbox (IMAP — any provider)
      ↓ scheduler.py polls per user (UID-based + SINCE date + UNSEEN — no missed emails)
PostgreSQL DB → processing_jobs (status: queued)
      ↓ worker.py picks up jobs (parallel OCR + per-user AI lock)
OCR (Tesseract / pdfplumber / LLaVA vision) → AI Crew (3 core agents)
      ↓ Extracts: sender, receiver, bank details, line items, financials
      ↓ Validates & auto-corrects calculations (line totals, subtotal, tax, total, amount due)
PostgreSQL DB → invoices (status: PENDING)
      ↓ User reviews in UI → Approve / Reject
Destinations: ERP Webhooks (parallel routing on approval)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI Engine | CrewAI — 3 core agents (intake, extraction, validation) |
| OCR | Tesseract (images) + pdfplumber (PDFs) + LLaVA vision model |
| LLM | Ollama (self-hosted) or any cloud model via LiteLLM |
| Backend | FastAPI + PostgreSQL (SQLAlchemy) |
| Frontend | React + TypeScript + Tailwind + shadcn/ui |
| Email | IMAP polling — UID-based with 48h lookback for missed emails |
| Deployment | Docker Hub image `shahnoor77/invoiceiq:latest` |

---

## Project Structure

```
├── api.py                  # FastAPI REST API — all /api/* endpoints
├── auth.py                 # JWT authentication helpers
├── database.py             # SQLAlchemy engine + session factory
├── models.py               # DB models: users, invoices, webhooks, jobs, email_configs
├── scheduler.py            # Email poller — UID-based, SINCE-date, UNSEEN safety net
├── worker.py               # Invoice processor — OCR, AI crew, validation, retry logic
├── destinations.py         # Routes approved invoices to webhooks in parallel
├── db_setup.py             # Database management CLI
├── Dockerfile              # Multi-stage: React build + Python backend (port 80)
├── docker-compose.yml      # Stack: API + PostgreSQL (pulls from Docker Hub)
├── .env.example            # Environment variable template
├── invoiceiq-dash/         # React frontend (TypeScript + Tailwind + shadcn/ui)
│   └── src/
│       ├── pages/          # Login, Invoices, InvoiceDetail, Settings
│       ├── components/     # UI components, settings forms
│       └── lib/api.ts      # All API calls
└── src/invoice_processing_automation_system/
    ├── crew.py             # CrewAI agents, ModelConfig, make_llm
    ├── config/
    │   ├── agents.yaml
    │   └── tasks.yaml      # Extraction prompt with strict line item rules
    └── tools/
        └── custom_tool.py  # PDFTextExtractor, ImageTextExtractor, LLaVA
```

---

## Quick Start — Docker (Recommended)

No build required — pulls the pre-built image from Docker Hub.

### 1. Create your `.env`

```bash
cp .env.example .env
# Edit .env with your values
```

### 2. Start the stack

```bash
docker compose pull
docker compose up -d
```

- App: `http://localhost` (port 80)
- API docs: `http://localhost/docs`

### 3. That's it

Tables are created automatically on first startup. Register an account at `http://localhost`.

---

## VM Deployment

Copy only these two files to your VM:

```
docker-compose.yml
.env
```

Then:

```bash
docker compose pull && docker compose up -d
```

Open port **80** on your VM firewall. Access at `http://<vm-ip>`.

For Ollama running on the same VM, set:
```
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

For Ollama on a separate VM:
```
OLLAMA_BASE_URL=http://<ollama-vm-ip>:11434
```

Make sure Ollama binds to `0.0.0.0`:
```bash
sudo systemctl edit ollama
# Add: Environment="OLLAMA_HOST=0.0.0.0:11434"
sudo systemctl restart ollama
```

---

## Local Development Setup

### Requirements
- Python 3.10–3.13 + [uv](https://docs.astral.sh/uv/)
- PostgreSQL 14+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (Windows) or `apt install tesseract-ocr` (Linux)
- Node.js 18+

### Steps

```bash
# 1. Install Python deps
uv sync

# 2. Create DB and tables
uv run python db_setup.py create-db
uv run python db_setup.py setup

# 3. Configure environment
cp .env.example .env
# Edit .env

# 4. Run API (from project root)
uv run uvicorn api:app --host 0.0.0.0 --port 8000 --reload --reload-exclude ".venv"

# 5. Run frontend (separate terminal)
cd invoiceiq-dash
npm install
npm run dev
```

Frontend: `http://localhost:8080` — proxies `/api/*` to the backend automatically.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `DB_PASSWORD` | Yes | Postgres password (used by docker-compose) |
| `JWT_SECRET_KEY` | Yes | Long random string for JWT signing |
| `MODEL` | Yes | LLM to use (see options below) |
| `OLLAMA_BASE_URL` | Ollama only | Your Ollama server URL |
| `MODEL_API_KEY` | Cloud models | API key for Groq/OpenAI/Gemini |
| `OPENAI_API_KEY` | No | Set to `fake-key` if not using OpenAI |

---

## Switching LLM Models

Set `MODEL` (and `MODEL_API_KEY` for cloud models) in `.env`:

```bash
MODEL=ollama/qwen3.5:9b              # self-hosted, best accuracy
MODEL=ollama/llama3.1:8b             # self-hosted, faster
MODEL=groq/llama-3.3-70b-versatile   # Groq free tier — very fast
MODEL=gemini/gemini-2.0-flash        # Google free tier
MODEL=openai/gpt-4o-mini             # OpenAI
```

Users can also override the model per-account in **Settings → AI Model** — stored in the DB, never touches the server environment.

---

## Database Management

```bash
uv run python db_setup.py setup       # First-time: create all tables
uv run python db_setup.py migrate     # Add missing columns (run after pulling updates)
uv run python db_setup.py status      # Show tables and row counts
uv run python db_setup.py create-db   # Create the PostgreSQL database
uv run python db_setup.py reset       # Drop and recreate all tables (deletes data!)
```

Always run `migrate` after pulling code updates that add new DB columns.

---

## API Endpoints

All endpoints are under `/api/` prefix.

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Login, get JWT |
| GET | `/api/invoices` | List user's invoices |
| GET | `/api/invoices/{id}` | Full invoice with line items + financials |
| POST | `/api/invoices/upload` | Upload invoice file → queued job |
| GET | `/api/invoices/jobs/{id}` | Poll job status |
| PATCH | `/api/invoices/{id}/approve` | Approve → routes to webhooks |
| PATCH | `/api/invoices/{id}/reject` | Reject with reason |
| GET | `/api/settings/email` | Get email config |
| PUT | `/api/settings/email` | Save IMAP email config |
| POST | `/api/settings/email/test` | Test IMAP connection |
| POST | `/api/settings/email/poll-now` | Trigger immediate email poll |
| GET | `/api/settings/webhooks` | List webhooks |
| POST | `/api/settings/webhooks` | Create ERP webhook |
| PUT | `/api/settings/webhooks/{id}` | Update webhook |
| DELETE | `/api/settings/webhooks/{id}` | Delete webhook |
| POST | `/api/settings/webhooks/{id}/test` | Test webhook |
| GET | `/api/settings/model` | Get per-user model config |
| PUT | `/api/settings/model` | Set custom model + API key |
| DELETE | `/api/settings/model` | Reset to system default |
| GET | `/api/health` | System health check |

---

## Webhook Payload

Sent to all configured webhooks on invoice approval:

```json
{
  "event": "invoice.approved",
  "timestamp": "2026-04-09T14:30:00Z",
  "approved_by": "User Name",
  "invoice": { "invoice_number": "INV-001", "invoice_date": "2026-04-01", "due_date": "2026-04-30" },
  "sender": {
    "name": "Vendor Ltd", "address": "...", "tax_id": "...",
    "bank": { "bank_name": "...", "iban": "...", "swift_bic": "...", "account_number": "..." }
  },
  "receiver": { "name": "Client Corp", "address": "..." },
  "line_items": [
    { "description": "Consulting Services", "quantity": 10, "unit_price": 150, "total": 1500 }
  ],
  "financials": {
    "currency": "USD", "subtotal": 1500, "tax_rate": 10, "tax_amount": 150,
    "discount_total": 0, "shipping": 0, "total_amount": 1650, "amount_due": 1650
  }
}
```

---

## Email Polling Strategy

The scheduler uses a layered approach to ensure no invoices are missed:

1. **UID-based** — fetches all emails with UID > last processed UID (catches everything new)
2. **SINCE date** — looks back 2 hours from last poll (catches emails during server restarts)
3. **UNSEEN** — always includes unread emails as a safety net
4. **Message-ID dedup** — never processes the same email twice regardless of read state

On first poll (or after a long gap), looks back **48 hours** to catch missed emails.

---

## Docker Image

```
shahnoor77/invoiceiq:latest   # latest stable
shahnoor77/invoiceiq:v1       # tagged release
```

To rebuild and push a new image:
```bash
docker build -t shahnoor77/invoiceiq:latest .
docker tag shahnoor77/invoiceiq:latest shahnoor77/invoiceiq:v1
docker push shahnoor77/invoiceiq:latest
docker push shahnoor77/invoiceiq:v1
```
