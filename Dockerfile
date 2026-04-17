# ── Stage 1: Build React frontend ─────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /app/invoiceiq-dash
COPY invoiceiq-dash/package*.json ./
RUN npm ci --silent
COPY invoiceiq-dash/ ./
RUN npm run build


# ── Stage 2: Python backend ────────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

# System dependencies for OCR and image processing
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    tesseract-ocr-eng \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* ./
COPY src ./src

# Install Python dependencies
RUN uv sync --frozen --no-dev

# Copy backend source
COPY api.py auth.py database.py models.py destinations.py \
     scheduler.py worker.py jobs.py db_setup.py password_encryption.py ./
COPY knowledge/ ./knowledge/
COPY .env.example ./.env.example

# Copy built frontend from stage 1
COPY --from=frontend-builder /app/invoiceiq-dash/dist ./static

# Expose port 80 — uvicorn serves both API and React static files
EXPOSE 80

# Non-sensitive runtime defaults — all overridable via docker-compose env_file
ENV OLLAMA_BASE_URL=http://host.docker.internal:11434
ENV OLLAMA_API_BASE=http://host.docker.internal:11434
ENV MODEL=ollama/qwen3.5:9b
ENV DATABASE_URL=postgresql://postgres:postgres@db:5432/invoice_db

# Run DB setup (creates tables if missing) then start the API
CMD ["sh", "-c", "uv run python db_setup.py setup && uv run uvicorn api:app --host 0.0.0.0 --port 80"]
