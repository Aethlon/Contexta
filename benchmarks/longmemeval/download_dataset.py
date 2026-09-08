"""Download and cache LongMemEval dataset from Hugging Face."""

import json
from pathlib import Path
import httpx

DATASET_DIR = Path(__file__).parent / "data"
ORACLE_URL = "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_oracle.json"
OUTPUT_FILE = DATASET_DIR / "longmemeval_oracle.json"


def download():
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    if OUTPUT_FILE.exists() and OUTPUT_FILE.stat().st_size > 1_000_000:
        print(f"Dataset already downloaded at {OUTPUT_FILE} ({OUTPUT_FILE.stat().st_size / 1024 / 1024:.2f} MB)")
        return OUTPUT_FILE

    print(f"Downloading LongMemEval dataset from {ORACLE_URL}...")
    with httpx.Client(follow_redirects=True, timeout=120.0) as client:
        with client.stream("GET", ORACLE_URL) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))
            downloaded = 0
            with open(OUTPUT_FILE, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = (downloaded / total) * 100
                        print(f"\rProgress: {pct:.1f}% ({downloaded / 1024 / 1024:.2f} / {total / 1024 / 1024:.2f} MB)", end="", flush=True)

    print()
    print(f"Downloaded successfully: {OUTPUT_FILE} ({OUTPUT_FILE.stat().st_size / 1024 / 1024:.2f} MB)")

    # Validate JSON
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)
    print(f"Validated JSON: {len(data)} evaluation instances found.")
    return OUTPUT_FILE


if __name__ == "__main__":
    download()
