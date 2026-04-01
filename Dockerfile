FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

# System dependencies (for OCR/image processing)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock* ./
COPY src ./src

# Install dependencies using uv (fast, parallel downloads)
RUN uv sync --frozen --no-dev

# Copy the rest of the project
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Environment defaults (can be overridden at runtime)
ENV OPENAI_API_KEY=fake-key
ENV OLLAMA_BASE_URL=http://110.39.187.178:11434

# Run using uv so it uses the managed venv
CMD ["uv", "run", "streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
