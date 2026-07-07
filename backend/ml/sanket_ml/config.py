from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MLSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="ML_",
    )

    # ── Service-to-service auth ──────────────────────────────────────────────
    # The inference API is internal-only and must never be reached directly by a
    # browser: every request body carries a tenant_id that is pushed into the RLS
    # GUC, so an unauthenticated caller could read any tenant's data. The trusted
    # SANKET backend presents this shared secret as `Authorization: Bearer ...`.
    # `require_auth` defaults True; it may be disabled only for isolated local
    # runs (ML_REQUIRE_AUTH=false) where the port is not exposed.
    service_token: str | None = Field(default=None)  # ML_SERVICE_TOKEN
    require_auth: bool = Field(default=True)  # ML_REQUIRE_AUTH

    # Database (sync URL for pandas/SQLAlchemy)
    database_url: str = Field(
        default="postgresql://sanket_app:changeme@localhost:5432/sanket"
    )
    database_async_url: str = Field(
        default="postgresql+asyncpg://sanket_app:changeme@localhost:5432/sanket"
    )

    # Artifact storage
    artifact_root: Path = Field(default=Path("artifacts"))
    model_registry_uri: str = Field(default="file:./mlruns")
    experiment_name: str = "sanket-forecasting"

    # Training
    default_horizon_weeks: int = 26
    default_history_weeks: int = 156
    default_freq: Literal["D", "W", "M"] = "W"
    train_test_gap_weeks: int = 0
    cv_n_splits: int = 5
    random_seed: int = 42

    # Compute
    device: Literal["cpu", "cuda", "mps", "auto"] = "auto"
    n_jobs: int = -1
    torch_num_threads: int = 4

    # Foundation models — Hugging Face repo IDs
    timesfm_repo: str = "google/timesfm-1.0-200m-pytorch"
    chronos_repo: str = "amazon/chronos-t5-large"
    moirai_repo: str = "Salesforce/moirai-1.1-R-large"
    lag_llama_repo: str = "time-series-foundation-models/Lag-Llama"

    # Pinned Hugging Face revisions (supply-chain hardening, CWE-494).
    # Downloads MUST pass an explicit revision so a mutated upstream branch can
    # never silently swap model weights underneath us. These default to the
    # upstream release branch but SHOULD be pinned to an immutable commit SHA in
    # production via the matching env vars (e.g. ML_CHRONOS_REVISION=<sha>).
    timesfm_revision: str = Field(default="main")  # ML_TIMESFM_REVISION
    chronos_revision: str = Field(default="main")  # ML_CHRONOS_REVISION
    moirai_revision: str = Field(default="main")  # ML_MOIRAI_REVISION
    lag_llama_revision: str = Field(default="main")  # ML_LAG_LLAMA_REVISION

    hf_cache_dir: Path = Field(default=Path(".cache/huggingface"))

    # Distributed training
    use_ray: bool = False
    ray_address: str | None = None

    # Drift monitoring
    drift_alert_psi_threshold: float = 0.2
    drift_alert_kl_threshold: float = 0.1

    # Censored-demand (stockout) correction — unconstrains lost sales before
    # training so the models don't learn that a stockout means demand collapsed.
    censoring_enabled: bool = True
    censoring_availability_threshold: float = 0.5  # in-stock fraction below this = OOS
    censoring_heuristic_when_missing: bool = True   # fall back to ADI/CV² zero detection
    censoring_local_window: int = 8                 # periods for local demand estimate
    censoring_seasonal_period: int = 52             # weeks per cycle for seasonal index
    censoring_min_history: int = 12                 # skip series shorter than this

    # Zero-shot fallback (used when no trained artifacts exist for a tenant)
    chronos_preload_on_startup: bool = True
    zero_shot_default_context_weeks: int = 104
    zero_shot_num_samples: int = 100
    zero_shot_min_observations: int = 8
    # Cap on number of series per zero-shot request to keep cold inference bounded.
    zero_shot_max_series: int = 500

    # ── Inference DoS protection / admission control ─────────────────────────
    # Forecasting is CPU-heavy and can take tens of seconds. Without bounds a
    # handful of large requests saturate every ML replica and starve everyone
    # else. These limits are enforced PER ML REPLICA (the service is stateless;
    # with N replicas effective global capacity is N×).
    #
    # max_concurrent_inferences : forecasts actually executing at once. The
    #   heavy compute is offloaded to a thread pool and bounded by a semaphore so
    #   the event loop stays responsive to /health and rejections.
    # max_queued_inferences     : requests allowed to WAIT for a slot. Beyond
    #   (concurrent + queued) the service sheds load with HTTP 429 immediately
    #   rather than letting latency grow unbounded.
    # tenant_rate_limit_per_min : per-tenant token bucket so one noisy tenant
    #   cannot consume the whole replica's capacity (fairness + abuse control).
    inference_max_concurrent: int = Field(default=4, ge=1, le=64)
    inference_max_queued: int = Field(default=16, ge=0, le=1024)
    inference_tenant_rate_per_min: int = Field(default=30, ge=1)
    inference_tenant_burst: int = Field(default=10, ge=1)
    # Hard ceiling on how long a request may wait for a slot before giving up.
    inference_acquire_timeout_s: float = Field(default=20.0, ge=0.5)


@lru_cache(maxsize=1)
def get_ml_settings() -> MLSettings:
    return MLSettings()
