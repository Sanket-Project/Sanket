# syntax=docker/dockerfile:1.7
# ── SANKET Backend API (FastAPI) ────────────────────────────────────────────
# Multi-stage: builder installs deps into a venv that the runtime stage copies.

ARG PYTHON_VERSION=3.12-slim-bookworm@sha256:8a7e7cc04fd3e2bd787f7f24e22d5d119aa590d429b50c95dfe12b3abe52f48b

FROM python:${PYTHON_VERSION} AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
# Reproducible install: resolve from the committed uv.lock (pinned, hashed)
# rather than re-resolving floating ">=" constraints at build time. A drifted
# lock fails the build (`--frozen`) instead of silently shipping new versions.
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.10.11 \
 && python -m venv /opt/venv \
 && UV_PROJECT_ENVIRONMENT=/opt/venv \
    uv sync --frozen --no-dev --extra signals --no-install-project

# ── runtime ─────────────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r sanket && useradd -r -g sanket -d /app -s /sbin/nologin sanket

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY app ./app
COPY ml/sanket_ml ./sanket_ml
COPY sql ./sql
COPY alembic.ini ./
COPY alembic ./alembic
RUN chown -R sanket:sanket /app

USER sanket
EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
# FORWARDED_ALLOW_IPS: Set to your load balancer's CIDR (e.g. "10.0.0.0/8" for GCP internal LB).
# WARNING: Do NOT set to '*' — that allows any client to spoof X-Forwarded-For and bypass
# rate limiting. The default (127.0.0.1) is safe and correct when a trusted proxy sets headers.
# WORKERS: Number of uvicorn worker processes. Default 4 for production (2*CPU+1 is the formula).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WORKERS:-4} --proxy-headers --forwarded-allow-ips ${FORWARDED_ALLOW_IPS:-127.0.0.1} --timeout-keep-alive 65"]
