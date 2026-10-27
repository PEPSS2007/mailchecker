# Multi-stage production Dockerfile for Email Deliverability Checker
FROM python:3.12-slim AS builder

WORKDIR /app

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install build dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final runtime image
FROM python:3.12-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH" \
    PORT=8000

# Copy installed Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application source code
COPY app/ ./app/
COPY pyproject.toml .
COPY README.md .

# Create non-root user for security
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -s /bin/sh -m appuser && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

# Bind to 0.0.0.0 and dynamically honor Render's assigned $PORT
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
