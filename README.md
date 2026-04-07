# Automatic Invoice Processor

An AI-powered invoice processing system that automatically fetches invoices from email, extracts structured data using OCR and LLM agents, stores them in a database, and routes approved invoices to ERP systems, Slack, or email.

## Architecture

```
Email Inbox (IMAP)
      ↓ scheduler.py (polls every 1 min per user)
PostgreSQL DB (processing_jobs)
      ↓ worker.py (picks up queued jobs)
OCR + CrewAI Agents (extract invoice data)
      ↓
PostgreSQL DB (invoices — status: PENDING)
      ↓ User approves in UI
Destinations: ERP Webhook / Slack / Email
```

## Tech Stack

- **AI Engine**: CrewAI with 5 agents — intake, extraction, validation, ERP integration, notification
- **OCR**: Tesseract (images) + pdfplumber (PDFs) + LLaVA vision model (optional)
- **LLM**: Ollama (offline) or any cloud model via LiteLLM (Groq, OpenAI, Gemini)
- **Backend**: FastAPI + PostgreSQL (SQLAlchemy)
- **Frontend**: React + TypeScript + Tailwind + shadcn/ui (`invoiceiq-dash/`)
- **Email**: IMAP polling with auto-detection of provider settings

## Project Structure

```
├── api.py                  # FastAPI REST API (all endpoints)
├── auth.py                 # JWT authentication
├── database.py             # SQLAlchemy engine + session
├── models.py               # DB models: users, invoices, webhooks, jobs
├── scheduler.py            # Email poller — runs every 30s, polls per user
├── worker.py               # Invoice processor — picks up queued jobs
├── destinations.py         # Routes approved invoices to ERP/Slack/email
├── jobs.py                 # In-memory job queue (legacy, DB-backed now)
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
├── Dockerfile              # Docker build
├── docker-compose.yml      # Docker compose
├── invoiceiq-dash/         # React frontend (TypeScript + Tailwind)
│   ├── src/
│   │   ├── pages/          # Login, Invoices, InvoiceDetail, Settings
│   │   ├── components/     # UI components (shadcn/ui based)
│   │   ├── lib/api.ts      # All API calls in one file
│   │   └── context/        # Auth context
│   └── vite.config.ts      # Vite config with API proxy
├── src/invoice_processing_automation_system/
│   ├── crew.py             # CrewAI agents and tasks
│   ├── config/
│   │   ├── agents.yaml     # Agent roles and goals
│   │   └── tasks.yaml      # Task descriptions
│   └── tools/
│       └── custom_tool.py  # PDFTextExtractor, ImageTextExtractor, LLaVA
└── knowledge/
    └── user_preference.txt # Few-shot examples for agents
```

## Setup

### Requirements
- Python 3.10–3.13
- [uv](https://docs.astral.sh/uv/) package manager
- PostgreSQL 14+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (Windows) or `apt install tesseract-ocr` (Linux)
- Node.js 18+ (for frontend)
- An Ollama VM or cloud model API key

### 1. Clone and install

```bash
git clone https://github.com/shahnoor77/automatic-invoice-processor.git
cd automatic-invoice-processor
pip install uv
uv sync
```

### 2. Create PostgreSQL database

In pgAdmin or psql:
```sql
CREATE DATABASE invoice_db;
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Description |
|---|---|
| `DATABASE_URL` | `postgresql://postgres:password@localhost:5432/invoice_db` |
| `MODEL` | LLM to use — see options below |
| `OLLAMA_BASE_URL` | URL of your Ollama server (if using offline model) |
| `MODEL_API_KEY` | API key for cloud models |
| `GOOGLE_CREDENTIALS_FILE` | Path to Google service account JSON (optional, for Sheets export) |
| `GOOGLE_SHEET_ID` | Google Sheet ID (optional) |
| `SMTP_USER` | Gmail address for email notifications |
| `SMTP_PASSWORD` | Gmail App Password |
| `JWT_SECRET_KEY` | Random secret for JWT tokens |

### 4. Run the API

```bash
uv run uvicorn api:app --reload --port 8000
```

Tables are created automatically on first startup. API docs at `http://localhost:8000/docs`.

### 5. Run the frontend

```bash
cd invoiceiq-dash
npm install
npm run dev
```

Open `http://localhost:8080`

---

## Switching LLM Models

Change `MODEL` in `.env` — no code changes needed:

```bash
# Offline (Ollama)
MODEL=ollama/qwen3.5:9b          # recommended accuracy
MODEL=ollama/llama3.1:8b         # faster

# Cloud (free tiers)
MODEL=groq/llama-3.3-70b-versatile
MODEL=gemini/gemini-2.0-flash
MODEL=openai/gpt-4o-mini
```

---

## How It Works

### Automatic Email Processing
1. User configures their email in Settings (Gmail/Outlook/Yahoo — just email + password)
2. Scheduler polls their inbox every minute for new emails with PDF/image attachments
3. Attachments are downloaded and queued as `ProcessingJob` records
4. Worker picks up queued jobs, runs OCR + AI crew, saves extracted data as `PENDING` invoice

### Manual Upload
1. User uploads a PDF/PNG/JPG via the UI
2. Same processing pipeline runs asynchronously
3. Result appears in the Invoices list as `PENDING`

### Approval Flow
1. User reviews extracted invoice data in the UI
2. Clicks Approve → invoice status updates to `APPROVED`
3. System routes to all configured destinations simultaneously:
   - ERP webhook (POST JSON)
   - Slack (formatted message)
   - Email notification (SMTP)
4. Reject → status updates to `REJECTED` with reason logged

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Create account |
| POST | `/auth/login` | Login, get JWT token |
| GET | `/invoices` | List user's invoices |
| GET | `/invoices/{id}` | Get invoice detail |
| POST | `/invoices/upload` | Upload invoice file |
| GET | `/invoices/jobs/{id}` | Poll processing job status |
| PATCH | `/invoices/{id}/approve` | Approve + route to destinations |
| PATCH | `/invoices/{id}/reject` | Reject with reason |
| GET | `/settings/email` | Get email config |
| PUT | `/settings/email` | Save email config |
| POST | `/settings/email/test` | Test IMAP connection |
| POST | `/settings/email/poll-now` | Trigger immediate email poll |
| GET | `/settings/webhooks` | List webhooks |
| POST | `/settings/webhooks` | Create webhook |
| PUT | `/settings/webhooks/{id}` | Update webhook |
| DELETE | `/settings/webhooks/{id}` | Delete webhook |
| POST | `/settings/webhooks/{id}/test` | Test webhook |
| GET | `/health` | System health check |

Full interactive docs: `http://localhost:8000/docs`

---

## Docker (Production)

```bash
docker build -t invoice-processor .
docker compose up
```

For Ollama VM access from Docker, bind Ollama to `0.0.0.0`:
```bash
# On the Ollama VM
sudo systemctl edit ollama
# Add: Environment="OLLAMA_HOST=0.0.0.0:11434"
sudo systemctl restart ollama
```

---

## For Team Members

1. Clone the repo
2. Install PostgreSQL locally, create `invoice_db`
3. Copy `.env.example` → `.env`, fill in your DB password and model config
4. Get `google_credentials.json` from project owner if needed (not in repo)
5. Install Tesseract OCR
6. Run `uv sync` then `uv run uvicorn api:app --reload --port 8000`
7. In another terminal: `cd invoiceiq-dash && npm install && npm run dev`

---

## Known Limitations & Improvement Opportunities

- **Auth is JWT only** — no OAuth, no password reset. Replace with a proper auth service for production.
- **OCR accuracy** — Tesseract misreads digits on low-quality scans. Use GPT-4o vision or Gemini for near-perfect extraction.
- **In-memory job queue** — `jobs.py` is legacy. All jobs now use the DB but the old in-memory dict is still imported. Clean up when stable.
- **No duplicate detection** — same invoice can be processed twice if emailed again. Add hash-based dedup.
- **Webhook retry** — failed webhooks are logged but not retried. Add retry logic for production.
