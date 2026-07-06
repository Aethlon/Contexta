from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("contexta.buffer")

DEFAULT_BUFFER_DIR = Path.home() / ".contexta"
MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_ENTRIES = 1000
FLUSH_BATCH_SIZE = 50


class DurableBuffer:
    def __init__(self, buffer_path: Optional[str] = None, enabled: bool = True) -> None:
        self.enabled = enabled
        if not enabled:
            self.buffer_file: Optional[Path] = None
            self.dead_letter_file: Optional[Path] = None
            return
        buffer_dir = Path(buffer_path).parent if buffer_path else DEFAULT_BUFFER_DIR
        buffer_dir.mkdir(parents=True, exist_ok=True)
        self.buffer_file = buffer_path if buffer_path else buffer_dir / "buffer.jsonl"
        self.buffer_file = Path(self.buffer_file) if not isinstance(self.buffer_file, Path) else self.buffer_file
        self.dead_letter_file = buffer_dir / "dead-letter.jsonl"

    def enqueue(self, endpoint: str, body: Dict[str, Any], idempotency_key: str, headers: Dict[str, str]) -> None:
        if not self.enabled or not self.buffer_file:
            return
        entry = {
            "endpoint": endpoint,
            "body": body,
            "idempotency_key": idempotency_key,
            "headers": headers,
            "created_at": time.time(),
        }
        try:
            self._rotate_if_needed()
            with open(self.buffer_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as e:
            logger.warning("Failed to buffer observation: %s", e)

    def dequeue_all(self) -> List[Dict[str, Any]]:
        if not self.enabled or not self.buffer_file or not self.buffer_file.exists():
            return []
        try:
            with open(self.buffer_file, "r", encoding="utf-8") as f:
                entries = [json.loads(line) for line in f if line.strip()]
            self.buffer_file.unlink(missing_ok=True)
            return entries
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to read buffer: %s", e)
            return []

    def dead_letter(self, entry: Dict[str, Any], reason: str) -> None:
        if not self.enabled or not self.dead_letter_file:
            return
        entry["dead_letter_reason"] = reason
        entry["dead_lettered_at"] = time.time()
        try:
            with open(self.dead_letter_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as e:
            logger.warning("Failed to write dead-letter: %s", e)

    def flush(self, http_client: Any) -> int:
        if not self.enabled:
            return 0
        entries = self.dequeue_all()
        if not entries:
            return 0
        flushed = 0
        for i in range(0, len(entries), FLUSH_BATCH_SIZE):
            batch = entries[i : i + FLUSH_BATCH_SIZE]
            try:
                for entry in batch:
                    resp = http_client._request(
                        method="POST",
                        endpoint=entry["endpoint"],
                        body=entry["body"],
                        idempotency_key=entry["idempotency_key"],
                        headers=entry.get("headers"),
                    )
                    flushed += 1
            except Exception:
                for entry in batch:
                    self.dead_letter(entry, "flush_failure")
        return flushed

    def _rotate_if_needed(self) -> None:
        if not self.buffer_file or not self.buffer_file.exists():
            return
        try:
            size = self.buffer_file.stat().st_size
            if size > MAX_FILE_SIZE:
                self._rotate()
                return
            with open(self.buffer_file, "r", encoding="utf-8") as f:
                count = sum(1 for _ in f)
            if count > MAX_ENTRIES:
                self._rotate()
        except OSError:
            pass

    def _rotate(self) -> None:
        if not self.buffer_file:
            return
        rotated = self.buffer_file.with_suffix(".jsonl.old")
        try:
            if rotated.exists():
                rotated.unlink()
            self.buffer_file.rename(rotated)
        except OSError as e:
            logger.warning("Failed to rotate buffer: %s", e)
