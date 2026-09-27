"""Backfill `embedding_1024` + embedding profile metadata for memories missing them.

The Qwen3-1024 profile reads from `memory_record.embedding_1024`, but every existing
row has its vector in the legacy `embedding` column, so the dense retrieval layer
matches nothing. This dispatches the existing `generate_memory_embeddings` Celery
task in chunks to re-embed those rows with the active profile.

Safe to re-run: it only selects rows that still lack the profile column.
"""

import argparse
import subprocess
import sys
import time

SELECT_SQL = """
SELECT id FROM memory_record
WHERE embedding_1024 IS NULL
  AND valid_to IS NULL
ORDER BY created_at
LIMIT {limit} OFFSET {offset};
"""

COUNT_SQL = """
SELECT count(*) FROM memory_record
WHERE embedding_1024 IS NULL AND valid_to IS NULL;
"""


def psql(sql: str) -> str:
    out = subprocess.run(
        ["docker", "exec", "memento-postgres-1", "psql", "-U", "postgres",
         "-d", "contexta", "-t", "-A", "-c", sql],
        capture_output=True, text=True, check=False,
    )
    return out.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunk", type=int, default=100)
    parser.add_argument("--max-chunks", type=int, default=0, help="0 = all")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    remaining = int(psql(COUNT_SQL) or 0)
    print(f"rows needing a profile vector: {remaining}")
    if remaining == 0:
        print("nothing to do")
        return 0
    if args.dry_run:
        return 0

    from contexta.workers.embedding_tasks import generate_memory_embeddings

    total_chunks = (remaining + args.chunk - 1) // args.chunk
    if args.max_chunks:
        total_chunks = min(total_chunks, args.max_chunks)
    print(f"dispatching {total_chunks} chunk(s) of {args.chunk}")

    dispatched = 0
    started = time.perf_counter()
    for index in range(total_chunks):
        offset = index * args.chunk
        ids = [line for line in psql(
            SELECT_SQL.format(limit=args.chunk, offset=offset)
        ).splitlines() if line.strip()]
        if not ids:
            break
        generate_memory_embeddings.delay(ids)
        dispatched += len(ids)
        if (index + 1) % 10 == 0 or index + 1 == total_chunks:
            elapsed = time.perf_counter() - started
            print(f"  chunk {index + 1}/{total_chunks} dispatched={dispatched} "
                  f"elapsed={elapsed:.0f}s", flush=True)

    print(f"done: dispatched {dispatched} rows across {total_chunks} chunks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
