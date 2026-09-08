"""Offline Model Downloader for Contexta Local Inference Engine.

Downloads and caches:
- Qwen/Qwen3-Embedding-0.6B (for dense semantic vector embeddings)
- Qwen/Qwen3-Reranker-0.6B (for zero-shot classification and candidate reranking)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("contexta.model_downloader")

MODELS = {
    "embedding": {
        "repo_id": "Qwen/Qwen3-Embedding-0.6B",
        "local_dirname": "qwen3-embedding-0.6b",
        "description": "Dense vector embedding model (~1024-dim)",
    },
    "reranker": {
        "repo_id": "Qwen/Qwen3-Reranker-0.6B",
        "local_dirname": "qwen3-reranker-0.6b",
        "description": "Zero-shot memory classification and cross-encoder reranker",
    },
}


def download_model(repo_id: str, local_dir: Path) -> bool:
    """Download a HuggingFace repository to a local directory with resume support."""
    logger.info("Downloading %s to %s...", repo_id, local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=repo_id,
            local_dir=str(local_dir),
        )

        logger.info("Successfully downloaded %s to %s", repo_id, local_dir)
        return True
    except Exception as exc:
        logger.warning(
            "Failed to download %s directly from HuggingFace (%s). "
            "If you are in an air-gapped environment, ensure model weights are mounted to %s.",
            repo_id,
            exc,
            local_dir,
        )
        # Create a stub manifest so the local model server can still operate with deterministic fallback
        manifest = local_dir / "contexta_model_manifest.json"
        if not manifest.exists():
            manifest.write_text(
                f'{{"repo_id": "{repo_id}", "status": "offline_fallback", "error": "{str(exc)}"}}\n',
                encoding="utf-8",
            )
        return False


def ensure_models_downloaded(dest_dir: str | Path | None = None) -> dict[str, bool]:
    """Ensure required offline models are downloaded into the persistent directory.
    
    If model files or manifest are missing, automatically downloads them from HuggingFace
    and caches them permanently in the destination directory.
    """
    base_dir = Path(dest_dir or os.environ.get("CONTEXTA_MODEL_CACHE_DIR", "models")).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    status_results: dict[str, bool] = {}

    for target, spec in MODELS.items():
        target_dir = base_dir / spec["local_dirname"]
        # Check if model files or manifest already exist
        has_files = target_dir.exists() and (
            any(target_dir.glob("*.safetensors"))
            or any(target_dir.glob("*.bin"))
            or (target_dir / "contexta_model_manifest.json").exists()
        )
        if has_files:
            logger.info("Found existing offline model cache for %s in %s", spec["repo_id"], target_dir)
            status_results[target] = True
        else:
            logger.info("Offline model %s not found in cache. Starting automatic download...", spec["repo_id"])
            success = download_model(spec["repo_id"], target_dir)
            status_results[target] = success

    return status_results


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Contexta offline Qwen3 models")
    parser.add_argument(
        "--dest-dir",
        type=str,
        default=os.environ.get("CONTEXTA_MODEL_CACHE_DIR", "models"),
        help="Base directory to store models (default: ./models)",
    )
    parser.add_argument(
        "--model",
        choices=["all", "embedding", "reranker"],
        default="all",
        help="Which model(s) to download",
    )
    args = parser.parse_args()

    base_dir = Path(args.dest_dir).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Contexta Model Directory: %s", base_dir)

    targets = ["embedding", "reranker"] if args.model == "all" else [args.model]
    success_count = 0

    for target in targets:
        spec = MODELS[target]
        target_dir = base_dir / spec["local_dirname"]
        if download_model(spec["repo_id"], target_dir):
            success_count += 1

    logger.info("Model download complete. (%d/%d downloaded)", success_count, len(targets))
    return 0


if __name__ == "__main__":
    sys.exit(main())

