# Invoice Processing Automation System

A multi-agent AI pipeline built with [CrewAI](https://crewai.com) that automatically extracts, validates, and stores structured data from invoice files (PDF, PNG, JPG).

## What it does

Upload an invoice → OCR extracts text → agents extract structured data → you approve or reject → approved invoices are saved to Google Sheets.

**Pipeline (5 agents):**
1. Document Intake — detects file type, calls OCR tools
2. Data Extraction — converts raw OCR text into structured JSON (sender, receiver, line items, totals)
3. Data Validation — verifies math, checks completeness, flags anomalies
4. ERP Integration — pushes validated data to your ERP system
5. Finance Notification — notifies the finance team via your chosen channel

**Key features:**
- Approval/rejection gate before any data reaches ERP
- Google Sheets history with full invoice data per row
- Math verification in Python (catches OCR digit misreads)
- OCR confidence scoring — flags low-quality scans
- Works with any LLM: Ollama (offline), Groq, OpenAI, Gemini

---

## Setup

### Requirements
- Python 3.10–3.13
- [uv](https://docs.astral.sh/uv/) package manager
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (Windows) or `apt install tesseract-ocr` (Linux)
- An Ollama VM or API key for a cloud model

### Install

```bash
pip install uv
uv sync
```

### Configure

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `MODEL` | Model to use — see `.env.example` for options |
| `OLLAMA_BASE_URL` | URL of your Ollama VM (if using offline model) |
| `MODEL_API_KEY` | API key for cloud models (Groq/OpenAI/Gemini) |
| `GOOGLE_CREDENTIALS_FILE` | Path to your Google service account JSON |
| `GOOGLE_SHEET_ID` | ID from your Google Sheet URL |

For Google Sheets: place your service account JSON in the project root and share the sheet with the service account email as Editor.

### Run

```bash
uv run streamlit run app.py
```

Open `http://localhost:8501`

---

## Switching models

Change `MODEL` in `.env` — no code changes needed:

```bash
MODEL=ollama/qwen3.5:9b              # offline, recommended
MODEL=ollama/llama3.1:8b             # offline, faster
MODEL=groq/llama-3.3-70b-versatile   # Groq free tier
MODEL=gemini/gemini-1.5-flash        # Google free tier
MODEL=openai/gpt-4o-mini             # OpenAI
```

---

## Docker (production)

```bash
docker build -t invoice-app .
docker compose up
```

For Docker to reach an Ollama VM, the VM must bind to `0.0.0.0:11434`:
```bash
# On the VM
sudo systemctl edit ollama
# Add: Environment="OLLAMA_HOST=0.0.0.0:11434"
sudo systemctl restart ollama
```

---

## Known limitations & improvement opportunities

Each stage below notes what the current approach does, where it falls short, and what a better approach would be.

### Stage 1 — OCR (image/PDF text extraction)

**Current:** Tesseract OCR with preprocessing (grayscale, upscale to 1500px, sharpen ×3, adaptive binarization).

**Limitations:**
- Tesseract misreads similar digits (`5`→`8`, `0`→`6`) on certain fonts and low-res scans
- Table structure is lost — line items come out as flat text, making extraction harder
- Handwritten invoices are not supported

**Better approach:**
- Use a vision-capable LLM (GPT-4o, Gemini 1.5 Pro, Claude 3.5) — pass the image directly, skip Tesseract entirely. These models read tables, handwriting, and mixed layouts natively with near-zero digit errors.
- For offline: [Surya OCR](https://github.com/VikParuchuri/surya) or [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) are significantly more accurate than Tesseract for invoices, especially for tables.

---

### Stage 2 — Data extraction

**Current:** Single agent receives raw OCR text and outputs JSON at `temperature=0`. Few-shot example in `knowledge/user_preference.txt`.

**Limitations:**
- Small models (7–9B) occasionally merge sender/receiver or misplace values when OCR text layout is unusual
- `qwen3.5:9b` is the best available offline option but still ~5% error rate on complex invoices
- JSON parsing relies on regex fallback when model adds extra text around the JSON

**Better approach:**
- Vision LLMs eliminate the OCR→text→JSON chain entirely — one call, image in, JSON out
- `gpt-4o-mini` or `claude-3-5-haiku` reduce error rate to <1% on structured extraction
- Use structured output / function calling (OpenAI, Anthropic, Gemini all support this natively) — guarantees valid JSON schema, no regex parsing needed
- For offline: `qwen2.5:14b` or `mistral-nemo:12b` are meaningfully better than 9B models for JSON extraction

---

### Stage 3 — Math validation

**Current:** Python-side verification after extraction — checks line item totals, subtotal, and grand total. Flags mismatches as warnings.

**Limitations:**
- Only catches arithmetic errors, not semantic errors (e.g. wrong tax rate applied)
- Does not auto-correct — human must review warnings manually

**Better approach:**
- This stage is already well-implemented in Python and doesn't need a better model
- Could add currency conversion validation and vendor database lookup for known vendors

---

### Stage 4 — ERP integration

**Current:** Agent reports integration status. Actual ERP push is a placeholder (Google Sheets append via `google_sheets/append_values` app).

**Limitations:**
- No real ERP API integration implemented yet
- No retry logic for failed pushes
- No duplicate detection (same invoice pushed twice)

**Better approach:**
- Implement direct API calls to SAP, QuickBooks, NetSuite, or Xero using their REST APIs
- Add invoice hash-based deduplication before pushing
- This stage doesn't need a better LLM — it needs real API integration code

---

### Stage 5 — Notifications

**Current:** Agent sends a notification summary via the configured channel. Uses `google_gmail/send_email` app.

**Limitations:**
- Notification language is overly dramatic for minor issues (flags missing optional fields as "CRITICAL")
- No Slack/Teams integration
- Email sending requires Gmail OAuth setup

**Better approach:**
- Replace the LLM agent with a simple Python template — notifications don't need AI
- Add Slack webhook support (one `requests.post` call, no auth needed)
- Separate blocking issues from warnings in the notification

---

### Overall architecture

**Current:** Sequential 5-agent CrewAI pipeline. OCR runs in Python before the crew to avoid context pollution.

**Simplification with better models:**
If using GPT-4o or Gemini 1.5 Pro, the entire pipeline collapses to 2 steps:
1. Vision model: image → structured JSON (replaces OCR + extraction + layout analysis)
2. Python: validate math, save to Sheets, send notification

The multi-agent approach adds value when using small offline models that need task decomposition. With frontier models, it adds latency and complexity without accuracy benefit.

---

## Project structure

```
├── app.py                          # Streamlit UI
├── Dockerfile                      # Docker build
├── docker-compose.yml              # Docker compose
├── .env.example                    # Environment template (copy to .env)
├── requirements.txt                # Python dependencies
├── google_credentials.json         # Google service account (not committed — get from project owner)
├── knowledge/
│   └── user_preference.txt         # Few-shot examples for agents
└── src/invoice_processing_automation_system/
    ├── crew.py                     # Agent and task definitions
    ├── sheets.py                   # Google Sheets integration
    ├── email_fetcher.py            # IMAP email fetcher (future use)
    ├── config/
    │   ├── agents.yaml             # Agent roles and goals
    │   └── tasks.yaml              # Task descriptions and expected outputs
    └── tools/
        └── custom_tool.py          # PDFTextExtractor, ImageTextExtractor (Tesseract)
```

---

## For your team

1. Clone the repo
2. Copy `.env.example` → `.env` and fill in values
3. Get `google_credentials.json` from the project owner (not in repo — share via secure channel)
4. Install Tesseract: [Windows installer](https://github.com/UB-Mannheim/tesseract/wiki) or `apt install tesseract-ocr` on Linux
5. Run `uv sync` then `uv run streamlit run app.py`
