from __future__ import annotations

from pathlib import Path

import pandas as pd
import structlog
import torch

from sanket_ml.config import MLSettings, get_ml_settings

log = structlog.get_logger(__name__)


def build_pretraining_corpus(
    panels: list[pd.DataFrame],
    *,
    out_path: Path,
    min_length: int = 64,
) -> Path:
    """Concatenate many tenant panels into a single corpus for foundation
    model fine-tuning. Output is a parquet of (unique_id, ds, y) rows.
    Caller is responsible for ensuring tenant boundaries / consent."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pieces: list[pd.DataFrame] = []
    for i, p in enumerate(panels):
        p = p[["unique_id", "ds", "y"]].copy()
        p["unique_id"] = p["unique_id"].astype(str) + f"_panel{i}"
        counts = p.groupby("unique_id").size()
        keep = counts[counts >= min_length].index
        p = p[p["unique_id"].isin(keep)]
        pieces.append(p)
    if not pieces:
        raise ValueError("No panels passed for pretraining")
    corpus = pd.concat(pieces, ignore_index=True)
    corpus.to_parquet(out_path, engine="pyarrow", index=False)
    log.info(
        "pretrain.corpus.built",
        n_panels=len(panels),
        n_series=corpus["unique_id"].nunique(),
        n_obs=len(corpus),
        path=str(out_path),
    )
    return out_path


def fine_tune_chronos(
    corpus_path: Path,
    *,
    base_repo: str | None = None,
    output_dir: Path,
    max_steps: int = 5000,
    learning_rate: float = 1e-4,
    settings: MLSettings | None = None,
) -> Path:
    """Fine-tune Chronos on a domain corpus. Wraps amazon/chronos-forecasting's
    training script. Requires GPU for realistic runs."""
    settings = settings or get_ml_settings()
    repo = base_repo or settings.chronos_repo
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from chronos.scripts.training.train import main as chronos_train  # type: ignore
    except ImportError:
        log.warning("chronos.train.unavailable",
                    msg="Install amazon-chronos-forecasting training extras to enable.")
        return output_dir

    if not torch.cuda.is_available():
        log.warning("chronos.train.no_gpu", msg="Running fine-tune on CPU — will be very slow.")

    cfg = {
        "training_data_paths": [str(corpus_path)],
        "probability": [1.0],
        "model_id": repo,
        "output_dir": str(output_dir),
        "max_steps": max_steps,
        "learning_rate": learning_rate,
        "context_length": 512,
        "prediction_length": 64,
        "per_device_train_batch_size": 8,
        "save_strategy": "steps",
        "save_steps": 1000,
        "logging_steps": 50,
        "torch_compile": False,
    }
    log.info("chronos.train.start", repo=repo, output=str(output_dir))
    chronos_train(cfg)  # type: ignore[misc]
    log.info("chronos.train.done", output=str(output_dir))
    return output_dir


def warmup_foundation_models(settings: MLSettings | None = None) -> dict[str, bool]:
    """Pre-download all foundation model weights so first request is fast."""
    settings = settings or get_ml_settings()
    from huggingface_hub import snapshot_download

    results: dict[str, bool] = {}
    for name, repo, revision in [
        ("timesfm", settings.timesfm_repo, settings.timesfm_revision),
        ("chronos", settings.chronos_repo, settings.chronos_revision),
        ("moirai", settings.moirai_repo, settings.moirai_revision),
        ("lag_llama", settings.lag_llama_repo, settings.lag_llama_revision),
    ]:
        try:
            # Pin the revision so a mutated upstream branch can never swap the
            # downloaded weights underneath us (CWE-494, supply-chain hardening).
            snapshot_download(
                repo_id=repo,
                revision=revision,
                cache_dir=str(settings.hf_cache_dir),
                local_files_only=False,
            )
            results[name] = True
            log.info("foundation.warmup.ok", model=name, repo=repo)
        except Exception as exc:
            results[name] = False
            log.error("foundation.warmup.failed", model=name, repo=repo, error=str(exc))
    return results
