from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx

DEFAULT_DATASET = Path(r"C:\Users\jenit\Downloads\contexta_extreme_200_conversations.csv")
DEFAULT_OUTPUT = Path("benchmarks/extraction/results")
DEFAULT_MODELS = (
    "hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M",
    "qwen3:4b-instruct-2507-q4_K_M",
)

CLAIM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "subject": {"type": "string"},
                    "predicate": {"type": "string"},
                    "object": {"type": "string"},
                    "memory_type": {
                        "type": "string",
                        "enum": [
                            "fact",
                            "preference",
                            "goal",
                            "event",
                            "pattern",
                            "rule",
                            "relationship",
                            "skill",
                            "project",
                            "episodic",
                            "procedural",
                            "contact",
                            "custom",
                        ],
                    },
                    "polarity": {
                        "type": "string",
                        "enum": ["positive", "negative", "uncertain"],
                    },
                    "status": {
                        "type": "string",
                        "enum": ["current", "superseded", "temporary", "unknown"],
                    },
                    "evidence": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "text",
                    "subject",
                    "predicate",
                    "object",
                    "memory_type",
                    "polarity",
                    "status",
                    "evidence",
                    "confidence",
                ],
            },
        }
    },
    "required": ["claims"],
}

SYSTEM_PROMPT = """You extract durable memories from a conversation.
Return JSON only, with no markdown or explanation.
Create one atomic claim per independent assertion.
Use only user-authored information; assistant text is context, not a user fact.
Preserve the exact source wording in evidence.
Do not answer questions embedded in the conversation.
Keep temporary visits, corrections, and superseded claims separate.
Resolve relative dates only when an explicit message date is present.
Use subject=the user when the speaker is first person.
Use memory_type preference for likes/dislikes, pattern for recurring behavior,
fact for stable attributes, event for time-bound occurrences, and rule for explicit instructions.
Use polarity positive, negative, or uncertain.
Use status current, superseded, temporary, or unknown.
"""

REQUIRED_FIELDS = (
    "text",
    "subject",
    "predicate",
    "object",
    "memory_type",
    "polarity",
    "status",
    "evidence",
    "confidence",
)


def read_rows(path: Path, limit: int) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows[:limit]


def balanced_json(value: str) -> Any | None:
    text = value.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
    for start in sorted(starts):
        try:
            parsed, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        return parsed
    return None


def parse_claims(raw: str) -> tuple[list[dict[str, Any]], str | None]:
    parsed = balanced_json(raw)
    if isinstance(parsed, list):
        parsed = {"claims": parsed}
    if not isinstance(parsed, dict):
        return [], "no_json_object"
    claims = parsed.get("claims")
    if not isinstance(claims, list):
        return [], "missing_claims_array"
    normalized: list[dict[str, Any]] = []
    for item in claims:
        if not isinstance(item, dict):
            continue
        if "claim" in item and "text" not in item:
            item = {**item, "text": item.get("claim", "")}
        normalized.append({field: item.get(field) for field in REQUIRED_FIELDS})
    return normalized, None


def expected_anchors(conversation: str) -> list[str]:
    lowered = conversation.casefold()
    anchors: list[str] = []
    if "old address" in lowered or "moved to manchester" in lowered:
        anchors.extend(["london", "manchester", "visit"])
    if "prefer go over rust" in lowered or "prefer rust for backend" in lowered:
        anchors.extend(["rust", "go", "backend", "small clis"])
    if "postgresql" in lowered and "sqlite" in lowered:
        anchors.extend(["postgresql", "sqlite", "production", "local"])
    if "next monday" in lowered:
        anchors.append("monday")
    if "birthday party" in lowered:
        anchors.extend(["birthday", "timezone"])
    if "subscription expires" in lowered:
        anchors.extend(["subscription", "expiry"])
    if "graduated last year" in lowered or "finished my coursework" in lowered:
        anchors.extend(["coursework", "degree"])
    if "moving to berlin" in lowered:
        anchors.extend(["berlin", "spring", "october"])
    return anchors


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def evaluate(
    conversation: str,
    claims: list[dict[str, Any]],
    parse_error: str | None,
    latency_ms: float,
) -> dict[str, Any]:
    fields_present = 0
    grounded = 0
    typed = 0
    polarized = 0
    status_present = 0
    combined: list[str] = []
    for claim in claims:
        values = [str(claim.get(field) or "").strip() for field in REQUIRED_FIELDS]
        if all(values):
            fields_present += 1
        if claim.get("memory_type"):
            typed += 1
        if claim.get("polarity"):
            polarized += 1
        if claim.get("status"):
            status_present += 1
        evidence = normalize(claim.get("evidence"))
        if evidence and evidence in normalize(conversation):
            grounded += 1
        combined.extend(values)
    combined_text = " ".join(combined)
    anchors = expected_anchors(conversation)
    covered = [anchor for anchor in anchors if anchor in combined_text.casefold()]
    return {
        "json_valid": parse_error is None,
        "parse_error": parse_error,
        "claim_count": len(claims),
        "complete_claim_rate": round(fields_present / len(claims), 4) if claims else 0.0,
        "evidence_grounded_rate": round(grounded / len(claims), 4) if claims else 0.0,
        "typed_rate": round(typed / len(claims), 4) if claims else 0.0,
        "polarity_rate": round(polarized / len(claims), 4) if claims else 0.0,
        "status_rate": round(status_present / len(claims), 4) if claims else 0.0,
        "anchor_total": len(anchors),
        "anchor_covered": len(covered),
        "anchor_coverage": round(len(covered) / len(anchors), 4) if anchors else None,
        "question_claim_count": sum(1 for claim in claims if "?" in str(claim.get("text", ""))),
        "latency_ms": round(latency_ms, 2),
    }


def call_model(
    client: httpx.Client,
    model: str,
    conversation: str,
    *,
    timeout: float,
    num_ctx: int,
    num_predict: int,
) -> tuple[str, float, dict[str, Any]]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": conversation},
        ],
        "stream": False,
        "format": CLAIM_SCHEMA,
        "think": False,
        "options": {
            "temperature": 0.0,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        },
    }
    started = time.perf_counter()
    response = client.post("http://localhost:11434/api/chat", json=body, timeout=timeout)
    elapsed = (time.perf_counter() - started) * 1000
    response.raise_for_status()
    payload = response.json()
    return str(payload.get("message", {}).get("content", "")), elapsed, payload


def run_model(
    model: str,
    rows: Iterable[dict[str, str]],
    output_dir: Path,
    *,
    timeout: float,
    num_ctx: int,
    num_predict: int,
) -> dict[str, Any]:
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", model)
    result_path = output_dir / f"{safe_name}.jsonl"
    metrics: list[dict[str, Any]] = []
    with httpx.Client() as client, result_path.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows, start=1):
            conversation = row["conversation"]
            record: dict[str, Any] = {
                "conversation_id": row.get("conversation_id"),
                "difficulty": row.get("difficulty"),
                "model": model,
            }
            try:
                raw, latency, payload = call_model(
                    client,
                    model,
                    conversation,
                    timeout=timeout,
                    num_ctx=num_ctx,
                    num_predict=num_predict,
                )
                claims, parse_error = parse_claims(raw)
                record["claims"] = claims
                record["raw_output"] = raw
                record["metrics"] = evaluate(conversation, claims, parse_error, latency)
                record["done_reason"] = payload.get("done_reason")
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                record["claims"] = []
                record["raw_output"] = ""
                record["metrics"] = evaluate(conversation, [], type(exc).__name__, 0.0)
                record["error"] = f"{type(exc).__name__}: {exc}"
            metrics.append(record["metrics"])
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            metric = record["metrics"]
            print(
                f"{model} {index:03d}/{len(list(rows)):03d} "
                f"json={metric['json_valid']} claims={metric['claim_count']} "
                f"grounded={metric['evidence_grounded_rate']:.2f} "
                f"anchors={metric['anchor_coverage']} "
                f"latency={metric['latency_ms']:.0f}ms",
                flush=True,
            )
    valid = [item for item in metrics if item["json_valid"]]
    return {
        "model": model,
        "count": len(metrics),
        "json_valid_rate": round(len(valid) / len(metrics), 4) if metrics else 0.0,
        "mean_claims": round(statistics.mean(item["claim_count"] for item in metrics), 3)
        if metrics
        else 0.0,
        "mean_complete_claim_rate": round(
            statistics.mean(item["complete_claim_rate"] for item in metrics), 4
        )
        if metrics
        else 0.0,
        "mean_evidence_grounded_rate": round(
            statistics.mean(item["evidence_grounded_rate"] for item in metrics), 4
        )
        if metrics
        else 0.0,
        "mean_anchor_coverage": round(
            statistics.mean(
                item["anchor_coverage"] for item in metrics if item["anchor_coverage"] is not None
            ),
            4,
        )
        if any(item["anchor_coverage"] is not None for item in metrics)
        else None,
        "question_claims": sum(item["question_claim_count"] for item in metrics),
        "p95_latency_ms": round(
            sorted(item["latency_ms"] for item in metrics)[max(0, int(len(metrics) * 0.95) - 1)],
            2,
        )
        if metrics
        else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Contexta claim extraction pilots")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--num-ctx", type=int, default=4096)
    parser.add_argument("--num-predict", type=int, default=1200)
    args = parser.parse_args()

    rows = read_rows(args.dataset, args.limit)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Loaded {len(rows)} rows from {args.dataset}")
    summaries = []
    for model in args.models:
        summaries.append(
            run_model(
                model,
                rows,
                args.output_dir,
                timeout=args.timeout,
                num_ctx=args.num_ctx,
                num_predict=args.num_predict,
            )
        )
    summary_path = args.output_dir / f"summary-{args.limit}.json"
    summary_path.write_text(
        json.dumps({"dataset": str(args.dataset), "limit": args.limit, "models": summaries}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summaries, indent=2))
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
