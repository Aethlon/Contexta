"""Test automatic offline model download and persistent cache directory management."""

import os
import shutil
import tempfile
from pathlib import Path
import pytest

from scripts.download_offline_models import ensure_models_downloaded, MODELS
from contexta.workers.model_server import LocalModelEngine


def _weights_available() -> bool:
    """True when at least one Qwen3 model already exists in the local cache."""
    cache = Path(os.environ.get("MODEL_CACHE_DIR") or (Path.home() / ".cache" / "contexta" / "models"))
    for spec in MODELS.values():
        model_dir = cache / spec["local_dirname"]
        if model_dir.exists() and (
            (model_dir / "contexta_model_manifest.json").exists()
            or any(model_dir.glob("*.safetensors"))
        ):
            return True
    return False


def test_ensure_models_downloaded_creates_persistent_cache():
    """Verify that ensure_models_downloaded checks and populates the cache directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        results = ensure_models_downloaded(tmp_path)
        
        # Verify both models are checked
        assert "embedding" in results
        assert "reranker" in results
        
        # Verify subdirectories were created persistently
        for spec in MODELS.values():
            model_dir = tmp_path / spec["local_dirname"]
            assert model_dir.exists(), f"Expected {model_dir} to exist"
            # Manifest or weights should be present
            manifest = model_dir / "contexta_model_manifest.json"
            safetensors = list(model_dir.glob("*.safetensors"))
            assert manifest.exists() or len(safetensors) > 0


@pytest.mark.asyncio
async def test_local_model_engine_warmup_verifies_persistent_cache(monkeypatch):
    """Verify LocalModelEngine warmup checks persistent model cache on startup."""
    if not _weights_available():
        pytest.skip(
            "Qwen3 weights are not in the local cache and the host cannot reach "
            "HuggingFace; this test exercises real model loading. Run it inside the "
            "compose stack, where model-server has the models, to cover this path."
        )
    with tempfile.TemporaryDirectory() as tmp_dir:
        monkeypatch.setenv("MODEL_CACHE_DIR", tmp_dir)
        engine = LocalModelEngine()
        assert engine.cache_dir == tmp_dir
        
        await engine.warm_up()
        try:
            assert engine.loaded_at is not None
            assert len(engine.download_status) >= 2
            assert "embedding" in engine.download_status
            assert "reranker" in engine.download_status
        finally:
            await engine.shutdown()
