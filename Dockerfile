# ============================================
# Stage 1: Builder
# ============================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies needed for faster-whisper / ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirement files first (cache-friendly layer)
COPY requirements.txt requirements-local.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-local.txt

# ============================================
# Stage 2: Runtime
# ============================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime-only system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY app.py run.py main.py ./
COPY shorts_generator/ ./shorts_generator/
COPY templates/ ./templates/
COPY static/ ./static/
COPY .env.example .env.example

# Create output directory
RUN mkdir -p /app/output && chmod 777 /app/output

# Environment
ENV PORT=5000
ENV HOST=0.0.0.0
ENV WORKERS=2
ENV FLASK_ENV=production

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:$PORT/api/status')" || exit 1

# Expose port
EXPOSE 5000

# Run with gunicorn (production) or fall back to run.py (waitress)
CMD ["gunicorn", "-w", "${WORKERS:-2}", "-b", "0.0.0.0:5000", "--timeout", "120", "run:app"]
