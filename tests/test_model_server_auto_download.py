"""Test automatic offline model download and persistent cache directory management."""

import os
import shutil
import tempfile
from pathlib import Path
import pytest

from scripts.download_offline_models import ensure_models_downloaded, MODELS
from contexta.workers.model_server import LocalModelEngine


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
