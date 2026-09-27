"""Build the SFT dataset from the reviewed gold extraction corpus.

Unlike the earlier silver pipeline, this needs no teacher model: the corpus ships
reviewed `target_memories` plus the items a correct extractor must drop. The
only work here is splitting, ordering and prompt formatting.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contract import (
    CATEGORIES,
    POLARITIES,
    REQUIRED_FIELDS,
    STATUSES,
    SYSTEM_PROMPT,
    normalize,
)

DEFAULT_DATASET = Path(r"C:\Users\jenit\Downloads\contexta_cortex_extraction_1000.csv")
DEFAULT_OUTPUT = Path("benchmarks/extraction/sft/data")


def read_rows(path: Path, limit: int) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows[:limit]


def bucket(record_id: str, folds: int) -> int:
    digest = hashlib.sha256(record_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % folds


def build_example(row: dict[str, str], memories: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = [{field: memory[field] for field in REQUIRED_FIELDS} for memory in memories]
    return {
        "record_id": row["record_id"],
        "difficulty": row.get("difficulty", ""),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": row["conversation"]},
            {"role": "assistant", "content": json.dumps({"memories": ordered}, ensure_ascii=False)},
        ],
        "memories": ordered,
    }


def audit_row(row: dict[str, str], memories: list[dict[str, Any]]) -> list[str]:
    """Return integrity problems that make a gold row unusable for training."""
    problems: list[str] = []
    conversation = normalize(row["conversation"])
    for index, memory in enumerate(memories):
        for field in REQUIRED_FIELDS:
            if not normalize(memory.get(field)):
                problems.append(f"claim{index}:empty_{field}")
        if memory.get("category") not in CATEGORIES:
            problems.append(f"claim{index}:bad_category:{memory.get('category')}")
        if memory.get("polarity") not in POLARITIES:
            problems.append(f"claim{index}:bad_polarity:{memory.get('polarity')}")
        if memory.get("status") not in STATUSES:
            problems.append(f"claim{index}:bad_status:{memory.get('status')}")
        text = normalize(memory.get("text"))
        if text and text not in conversation:
            problems.append(f"claim{index}:text_not_in_conversation")
    if not memories:
        problems.append("no_target_memories")
    return problems


def write_split(path: Path, examples: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(json.dumps(example, ensure_ascii=False) + "\n")
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Build SFT data from the gold extraction corpus")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--val-fold", type=int, default=0)
    parser.add_argument("--folds", type=int, default=10)
    args = parser.parse_args()

    rows = read_rows(args.dataset, args.limit or 10**9)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    train: list[dict[str, Any]] = []
    validation: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    dropped_categories: dict[str, int] = {}

    for row in rows:
        try:
            memories = json.loads(row["target_memories"])
        except json.JSONDecodeError as exc:
            problems.append({"record_id": row["record_id"], "problems": [f"bad_json:{exc}"]})
            continue
        row_problems = audit_row(row, memories)
        if row_problems:
            problems.append({"record_id": row["record_id"], "problems": row_problems})
            continue
        try:
            for item in json.loads(row.get("dropped_items") or "[]"):
                category = str(item.get("category", "unknown"))
                dropped_categories[category] = dropped_categories.get(category, 0) + 1
        except json.JSONDecodeError:
            pass
        example = build_example(row, memories)
        if bucket(row["record_id"], args.folds) == args.val_fold:
            validation.append(example)
        else:
            train.append(example)

    train_path = args.output_dir / "train.jsonl"
    val_path = args.output_dir / "val.jsonl"
    train_count = write_split(train_path, train)
    val_count = write_split(val_path, validation)

    report = {
        "dataset": str(args.dataset),
        "rows": len(rows),
        "train": train_count,
        "validation": val_count,
        "rejected": len(problems),
        "dropped_item_categories": dict(sorted(dropped_categories.items(), key=lambda item: -item[1])),
        "train_path": str(train_path),
        "val_path": str(val_path),
    }
    (args.output_dir / "build-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if problems:
        (args.output_dir / "rejected.jsonl").write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in problems) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
