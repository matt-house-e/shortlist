# syntax=docker/dockerfile:1

# Multi-stage build for smaller production image
FROM python:3.13-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Copy vendor dependencies (git submodules)
COPY vendor/ ./vendor/

# Install dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Install vendor packages (lattice)
RUN uv pip install -e ./vendor/lattice

# Production stage
FROM python:3.13-slim AS production

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY app/ ./app/
COPY public/ ./public/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY chainlit.md ./
COPY .chainlit/ ./.chainlit/
COPY vendor/ ./vendor/

# Set ownership
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

# Chainlit configuration
ENV CHAINLIT_HOST=0.0.0.0
ENV CHAINLIT_PORT=8000

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/auth/config')" || exit 1

# Run Chainlit
CMD ["chainlit", "run", "app/chat/handlers.py", "--host", "0.0.0.0", "--port", "8000"]
