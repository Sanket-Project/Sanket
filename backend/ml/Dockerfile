# syntax=docker/dockerfile:1.7
# ── SANKET ML Inference Service ─────────────────────────────────────────────
# Heavy: pulls torch, transformers, statsforecast, lightgbm, ortools.
# We split into a CPU-only base image; a CUDA variant lives in Dockerfile.gpu.

ARG PYTHON_VERSION=3.12-slim-bookworm@sha256:8a7e7cc04fd3e2bd787f7f24e22d5d119aa590d429b50c95dfe12b3abe52f48b

FROM python:${PYTHON_VERSION} AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ gfortran \
    libpq-dev libomp-dev \
    cmake git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip wheel \
 && /opt/venv/bin/pip install --extra-index-url https://download.pytorch.org/whl/cpu \
    "torch==2.6.*" \
 && /opt/venv/bin/pip install .

# Pre-warm Hugging Face cache so the image ships with Chronos weights
ARG CHRONOS_REPO=amazon/chronos-t5-small
ENV HF_HOME=/opt/hf-cache
RUN /opt/venv/bin/python -c "from huggingface_hub import snapshot_download; \
    snapshot_download('${CHRONOS_REPO}', cache_dir='/opt/hf-cache')" || \
    echo "WARN: could not pre-warm Chronos weights; first request will download."

# ── runtime ─────────────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/opt/hf-cache \
    OMP_NUM_THREADS=4 \
    MKL_NUM_THREADS=4

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 libgomp1 \
    curl tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r sanket && useradd -r -g sanket -d /app -s /sbin/nologin sanket

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/hf-cache /opt/hf-cache

WORKDIR /app
COPY sanket_ml ./sanket_ml
COPY scripts ./scripts
RUN mkdir -p /app/artifacts /app/mlruns \
 && chown -R sanket:sanket /app /opt/hf-cache

USER sanket
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=8s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8001}/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "exec uvicorn sanket_ml.inference.api:app --host 0.0.0.0 --port ${PORT:-8001} --workers 2 --proxy-headers"]
