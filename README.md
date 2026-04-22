# InvoiceIQ

> AI-powered invoice processing — extract, validate, review, and route invoices automatically.

InvoiceIQ connects to your email inbox, extracts structured data from invoice attachments using OCR and LLM agents, validates calculations, and routes approved invoices to your ERP or webhook endpoints. Everything runs in Docker with a single command.

---

## Features

- **Automatic email polling** — connects to any IMAP inbox (Gmail, Outlook, Yahoo, custom), fetches invoice attachments, and queues them for processing
- **Multi-layer OCR** — pdfplumber for text-based PDFs, Tesseract + LLaVA vision model for scanned/image invoices
- **AI extraction** — structured data extraction via CrewAI agents with automatic calculation validation and correction
- **Manual review UI** — approve, reject, or edit extracted invoice data before routing
- **Webhook routing** — send approved invoices to any ERP endpoint with configurable auth, headers, and payload templates
- **Per-user model config** — each user can override the system LLM with their own API key (Groq, OpenAI, Gemini, or custom Ollama)
- **Encrypted credentials** — email passwords stored with AES-GCM encryption
- **CI/CD** — GitHub Actions builds and pushes Docker images; Watchtower auto-deploys on the VM

---

## Architecture

```
Email Inbox (IMAP)
    ↓  scheduler.py — UID-based polling, 48h lookback, Message-ID dedup
PostgreSQL — processing_jobs (queued)
    ↓  worker.py — parallel OCR, per-user AI lock, retry logic
OCR (pdfplumber / Tesseract / LLaVA)
    ↓
CrewAI Agents — extraction → validation
    ↓
PostgreSQL — invoices (PENDING)
    ↓  User reviews in React UI
Approve → Webhooks (ERP, Slack)
Reject  → Logged with reason
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI Agents | CrewAI with LiteLLM |
| LLM | Ollama (self-hosted) · Groq · OpenAI · Gemini |
| OCR | pdfplumber · Tesseract · LLaVA vision |
| Backend | FastAPI · PostgreSQL · SQLAlchemy |
| Frontend | React · TypeScript · Tailwind CSS · shadcn/ui |
| Deployment | Docker · Docker Hub · Watchtower (auto-deploy) |
| CI/CD | GitHub Actions |

---

## Quick Start — Docker

No build required. Pulls the pre-built image from Docker Hub.

**1. Copy and configure environment**

```bash
cp .env.example .env
# Edit .env with your values
```

**2. Start the stack**

```bash
docker compose pull
docker compose up -d
```

**3. Access the app**

Open `http://localhost:85` and register an account.

Tables are created automatically on first startup. No manual DB setup needed.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `DB_PASSWORD` | Yes | Postgres password (used by docker-compose) |
| `JWT_SECRET_KEY` | Yes | Long random string for JWT signing |
| `MODEL` | Yes | LLM to use (see options below) |
| `OLLAMA_BASE_URL` | Ollama only | Your Ollama server URL |
| `MODEL_API_KEY` | Cloud models | API key for Groq / OpenAI / Gemini |
| `OPENAI_API_KEY` | No | Set to `fake-key` if not using OpenAI |
| `EMAIL_ENCRYPTION_KEY` | Recommended | Key for encrypting stored email passwords |
| `EMAIL_ENCRYPTION_SALT` | Recommended | Salt for key derivation |

Generate secure values for encryption keys:
```bash
python -c "import secrets; print(secrets.token_hex(32))"  # for KEY
python -c "import secrets; print(secrets.token_hex(16))"  # for SALT
```

---

## Switching LLM Models

Set `MODEL` in `.env`. Add `MODEL_API_KEY` for cloud providers.

```bash
MODEL=ollama/qwen3.5:9b              # self-hosted, default
MODEL=groq/llama-3.3-70b-versatile   # Groq free tier — fast
MODEL=gemini/gemini-2.0-flash        # Google free tier
MODEL=openai/gpt-4o-mini             # OpenAI
```

Users can also set their own model per-account in **Settings → AI Model**. Multiple configs can be saved and switched with one click.

---

## VM Deployment

Copy only two files to the VM:

```
docker-compose.yml
.env
```

Then:

```bash
docker compose pull && docker compose up -d
```

Open port **85** on the VM firewall. Access at `http://<vm-ip>:85`.

**Ollama on the same VM:**
```
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

**Ollama on a separate server:**
```
OLLAMA_BASE_URL=http://<ollama-server-ip>:11434
```

Make sure Ollama binds to all interfaces:
```bash
sudo systemctl edit ollama
# Add: Environment="OLLAMA_HOST=0.0.0.0:11434"
sudo systemctl restart ollama
```

---

## CI/CD — Auto Deploy

Every push to `main` triggers GitHub Actions to build and push `shahnoor77/invoiceiq:latest` to Docker Hub. Watchtower on the VM polls Docker Hub every 5 minutes and automatically redeploys when a new image is detected.

**GitHub Secrets required:**

| Secret | Value |
|---|---|
| `DOCKERHUB_USERNAME` | `docker username` |
| `DOCKERHUB_TOKEN` | Docker Hub access token (Account Settings → Security) |

Set these at: `github.com/<repo> → Settings → Secrets and variables → Actions`

---

## Local Development

**Requirements:** Python 3.10–3.13, [uv](https://docs.astral.sh/uv/), PostgreSQL 14+, Node.js 18+, [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)

```bash
# Install Python dependencies
uv sync

# Create DB and tables
uv run python db_setup.py create-db
uv run python db_setup.py setup

# Configure environment
cp .env.example .env

# Run API (from project root)
uv run uvicorn api:app --host 0.0.0.0 --port 8000 --reload --reload-exclude ".venv"

# Run frontend (separate terminal)
cd invoiceiq-dash
npm install
npm run dev
```

Frontend runs at `http://your-host:8080` and proxies `/api/*` to the backend automatically.

---

## Database Management

```bash
uv run python db_setup.py setup       # First-time: create all tables
uv run python db_setup.py migrate     # Add missing columns after pulling updates
uv run python db_setup.py status      # Show tables and row counts
uv run python db_setup.py create-db   # Create the PostgreSQL database
uv run python db_setup.py reset       # Drop and recreate all tables (deletes data)
```

Always run `migrate` after pulling code updates that add new DB columns.

---

## API Reference

All endpoints are under the `/api/` prefix.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Create account |
| `POST` | `/api/auth/login` | Login, receive JWT |
| `GET` | `/api/invoices` | List invoices |
| `GET` | `/api/invoices/{id}` | Invoice detail with line items |
| `POST` | `/api/invoices/upload` | Upload invoice file |
| `GET` | `/api/invoices/jobs/{id}` | Poll processing job status |
| `PATCH` | `/api/invoices/{id}/approve` | Approve → routes to webhooks |
| `PATCH` | `/api/invoices/{id}/reject` | Reject with reason |
| `PATCH` | `/api/invoices/{id}` | Edit invoice fields |
| `DELETE` | `/api/invoices/{id}` | Delete invoice |
| `GET` | `/api/settings/email` | Get email config |
| `PUT` | `/api/settings/email` | Save IMAP config |
| `POST` | `/api/settings/email/test` | Test IMAP connection |
| `POST` | `/api/settings/email/poll-now` | Trigger immediate poll |
| `PATCH` | `/api/settings/email/toggle` | Enable / disable polling |
| `GET` | `/api/settings/webhooks` | List webhooks |
| `POST` | `/api/settings/webhooks` | Create webhook |
| `PUT` | `/api/settings/webhooks/{id}` | Update webhook |
| `DELETE` | `/api/settings/webhooks/{id}` | Delete webhook |
| `POST` | `/api/settings/webhooks/{id}/test` | Test webhook |
| `GET` | `/api/settings/model` | Get model configs |
| `PUT` | `/api/settings/model` | Save and activate model config |
| `PATCH` | `/api/settings/model/{id}/activate` | Activate a saved config |
| `DELETE` | `/api/settings/model/{id}` | Delete a model config |
| `DELETE` | `/api/settings/model` | Reset to system default |
| `GET` | `/api/health` | System health check |

Interactive API docs: `http://your-host:85/docs`

---

## Webhook Payload

Sent to all active webhooks on invoice approval:

```json
{
  "event": "invoice.approved",
  "timestamp": "2026-04-17T10:00:00Z",
  "approved_by": "User Name",
  "invoice": {
    "invoice_number": "INV-001",
    "invoice_date": "2026-04-01",
    "due_date": "2026-04-30",
    "purchase_order": "PO-12345"
  },
  "sender": {
    "name": "Vendor Ltd",
    "address": "123 Main St",
    "tax_id": "TAX-001",
    "bank": {
      "bank_name": "HBL",
      "iban": "PK92HABB000000000000",
      "swift_bic": "HABBPKKA"
    }
  },
  "receiver": { "name": "Client Corp", "address": "456 Business Ave" },
  "line_items": [
    { "description": "Consulting Services", "quantity": 10, "unit_price": 150, "total": 1500 }
  ],
  "financials": {
    "currency": "USD",
    "subtotal": 1500,
    "tax_rate": 10,
    "tax_amount": 150,
    "discount_total": 0,
    "total_amount": 1650,
    "amount_due": 1650
  }
}
```

---

## Docker Image

```
shahnoor77/invoiceiq:latest   # always latest build
```

To manually build and push:
```bash
docker build --no-cache -t docker-hub-username/invoiceiq:latest . 
docker push docker-hub-username/invoiceiq:latest
```
