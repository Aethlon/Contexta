"""Make the SDK importable when the tests run from the repository root."""

from __future__ import annotations

import sys
from pathlib import Path

SDK_ROOT = Path(__file__).resolve().parents[1]
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))
