"""Build a silver SFT dataset for LFM2.5 claim extraction.

The teacher is Qwen3-4B-Instruct served by Ollama. Its raw output is only useful
as a training target after deterministic validation, because the teacher still
makes semantic errors on this dataset (superseded facts kept as current, meta
objects such as "address" instead of the real value, unresolved relative dates).

Every hard check DROPS a claim and every soft check REPAIRS a claim, and each
repair is logged so the resulting labels can be audited before training.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_extraction_benchmark as bench

MEMORY_TYPES = set(bench.CLAIM_SCHEMA["properties"]["claims"]["items"]["properties"]["memory_type"]["enum"])
POLARITIES = set(bench.CLAIM_SCHEMA["properties"]["claims"]["items"]["properties"]["polarity"]["enum"])
STATUSES = set(bench.CLAIM_SCHEMA["properties"]["claims"]["items"]["properties"]["status"]["enum"])

USER_PREFIX = re.compile(r"^user\s*(?:\((?P<date>\d{4}-\d{2}-\d{2})\))?\s*:\s*", re.IGNORECASE)
USER_DATE = re.compile(r"user\s*\((\d{4}-\d{2}-\d{2})\)\s*:", re.IGNORECASE)

META_OBJECTS = {
    "address",
    "location",
    "city",
    "place",
    "job",
    "company",
    "employer",
    "name",
    "team",
    "role",
    "title",
    "number",
    "date",
    "time",
    "price",
    "status",
    "value",
    "detail",
    "details",
    "it",
    "them",
    "this",
    "that",
}

SUPERSEDED_CUES = (
    "old address",
    "old ",
    "used to",
    "previously",
    "no longer",
    "former ",
    "before the move",
)

TEMPORARY_CUES = (
    "visiting",
    "for two weeks",
    "for a few weeks",
    "temporarily",
    "for the trip",
    "on holiday",
    "for the visit",
)

# The dataset repeats this line in every conversation. It is an instruction to the
# extractor, not a durable user memory, so it must never become a training label.
BOILERPLATE = re.compile(
    r"when i said ['\"]?then['\"]?.{0,40}previous event.{0,60}not the date immediately above",
    re.IGNORECASE | re.DOTALL,
)

# Imperative text aimed at the extractor is a prompt-injection style distractor.
DIRECTIVE = re.compile(
    r"\b(do not|don't|never|ignore|you should|you must|only when|resolve it only)\b",
    re.IGNORECASE,
)

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

PROPER_PLACE_PATTERNS = (
    re.compile(r"\blives? in ([A-Z][\w'-]+)"),
    re.compile(r"\bmoved to ([A-Z][\w'-]+)"),
    re.compile(r"\brelocated to ([A-Z][\w'-]+)"),
    re.compile(r"\bfrom ([A-Z][\w'-]+)"),
    re.compile(r"\bwas ([A-Z][\w'-]+)"),
    re.compile(r"\bis ([A-Z][\w'-]+)"),
    re.compile(r"\bto ([A-Z][\w'-]+)"),
    re.compile(r"\bin ([A-Z][\w'-]+)"),
    re.compile(r"\bat ([A-Z][\w'-]+)"),
)


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def split_conversation(conversation: str) -> tuple[str, str, list[date]]:
    """Return (user_text, assistant_text, user_message_dates)."""
    user_lines: list[str] = []
    assistant_lines: list[str] = []
    dates: list[date] = []
    for raw_line in conversation.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.casefold().startswith("assistant:"):
            assistant_lines.append(line.split(":", 1)[1].strip())
            continue
        match = USER_PREFIX.match(line)
        if match:
            dates_text = match.group("date")
            if dates_text:
                dates.append(date.fromisoformat(dates_text))
            user_lines.append(line[match.end() :])
        else:
            user_lines.append(line)
    if not dates:
        dates = [date.fromisoformat(value) for value in USER_DATE.findall(conversation)]
    return "\n".join(user_lines), "\n".join(assistant_lines), dates


def latest_date(dates: Iterable[date]) -> date | None:
    values = list(dates)
    return max(values) if values else None


def resolve_relative_dates(text: str, reference: date | None) -> str:
    """Replace unambiguous relative date phrases with concrete years/dates."""
    if reference is None:
        return text
    result = re.sub(r"\blast year\b", str(reference.year - 1), text, flags=re.IGNORECASE)
    result = re.sub(r"\bthis year\b", str(reference.year), result, flags=re.IGNORECASE)
    result = re.sub(r"\bnext year\b", str(reference.year + 1), result, flags=re.IGNORECASE)

    def weekday(match: re.Match[str]) -> str:
        target = WEEKDAYS.get(match.group(1).casefold())
        if target is None:
            return match.group(0)
        delta = (target - reference.weekday()) % 7 or 7
        return (reference + timedelta(days=delta)).isoformat()

    return re.sub(r"\bnext (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", weekday, result, flags=re.IGNORECASE)


def repair_object(claim: dict[str, Any], evidence: str) -> str | None:
    """Replace meta objects such as "address" with the concrete value."""
    obj = str(claim.get("object") or "").strip()
    if obj.casefold() not in META_OBJECTS:
        return None
    for pattern in PROPER_PLACE_PATTERNS:
        match = pattern.search(evidence)
        if match:
            value = match.group(1)
            if value.casefold() not in META_OBJECTS:
                return value
    return None


def validate_and_repair(
    conversation: str,
    user_text: str,
    assistant_text: str,
    reference: date | None,
    claims: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (kept_claims, dropped, repairs) for one conversation."""
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    repairs: list[dict[str, Any]] = []
    normalized_user = normalize(user_text)
    normalized_assistant = normalize(assistant_text)

    for claim in claims:
        values = {field: str(claim.get(field) or "").strip() for field in bench.REQUIRED_FIELDS}
        if not all(values.values()):
            dropped.append({"claim": claim, "reason": "incomplete_fields"})
            continue
        if values["memory_type"] not in MEMORY_TYPES:
            dropped.append({"claim": claim, "reason": f"bad_memory_type:{values['memory_type']}"})
            continue
        if values["polarity"] not in POLARITIES:
            dropped.append({"claim": claim, "reason": f"bad_polarity:{values['polarity']}"})
            continue
        if values["status"] not in STATUSES:
            dropped.append({"claim": claim, "reason": f"bad_status:{values['status']}"})
            continue
        try:
            confidence = float(values["confidence"])
        except ValueError:
            dropped.append({"claim": claim, "reason": "bad_confidence"})
            continue
        if not 0.0 <= confidence <= 1.0:
            dropped.append({"claim": claim, "reason": f"confidence_out_of_range:{confidence}"})
            continue
        if "?" in values["text"]:
            dropped.append({"claim": claim, "reason": "question_claim"})
            continue

        evidence_key = normalize(values["evidence"])
        if not evidence_key:
            dropped.append({"claim": claim, "reason": "empty_evidence"})
            continue
        cleaned_evidence = USER_PREFIX.sub("", values["evidence"]).strip()
        cleaned_key = normalize(cleaned_evidence)
        if cleaned_key in normalized_assistant and cleaned_key not in normalized_user:
            dropped.append({"claim": claim, "reason": "assistant_sourced_evidence"})
            continue
        if cleaned_key not in normalized_user:
            dropped.append({"claim": claim, "reason": "evidence_not_in_user_text"})
            continue
        if BOILERPLATE.search(cleaned_evidence):
            dropped.append({"claim": claim, "reason": "meta_instruction_boilerplate"})
            continue
        if DIRECTIVE.search(cleaned_evidence):
            dropped.append({"claim": claim, "reason": "directive_to_extractor"})
            continue
        values["evidence"] = cleaned_evidence

        fixed = dict(values)
        fixed["confidence"] = round(confidence, 2)

        original_text = fixed["text"]
        fixed["text"] = resolve_relative_dates(fixed["text"], reference)
        if fixed["text"] != original_text:
            repairs.append({"field": "text", "from": original_text, "to": fixed["text"]})

        original_object = fixed["object"]
        replacement = repair_object(fixed, values["evidence"])
        if replacement is not None:
            fixed["object"] = replacement
            repairs.append({"field": "object", "from": original_object, "to": replacement})
        elif original_object.casefold() in META_OBJECTS:
            dropped.append({"claim": claim, "reason": f"unresolved_meta_object:{original_object}"})
            continue

        evidence_lower = values["evidence"].casefold()
        claim_lower = f"{fixed['text']} {fixed['object']}".casefold()
        original_status = fixed["status"]
        if any(cue in claim_lower for cue in SUPERSEDED_CUES) and fixed["status"] == "current":
            fixed["status"] = "superseded"
        elif any(cue in evidence_lower for cue in TEMPORARY_CUES) and fixed["status"] == "current":
            fixed["status"] = "temporary"
        if fixed["status"] != original_status:
            repairs.append({"field": "status", "from": original_status, "to": fixed["status"]})

        if normalize(fixed["evidence"]) not in normalize(conversation):
            dropped.append({"claim": claim, "reason": "evidence_not_in_conversation"})
            continue

        kept.append(fixed)

    return kept, dropped, repairs


def main() -> int:
    parser = argparse.ArgumentParser(description="Build silver SFT data from a Qwen teacher")
    parser.add_argument("--dataset", type=Path, default=bench.DEFAULT_DATASET)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--teacher", default="qwen3:4b-instruct-2507-q4_K_M")
    parser.add_argument("--output-dir", type=Path, default=Path("benchmarks/extraction/sft/data"))
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--num-ctx", type=int, default=4096)
    parser.add_argument("--num-predict", type=int, default=900)
    args = parser.parse_args()

    rows = bench.read_rows(args.dataset, args.limit)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    train_path = args.output_dir / "silver-train.jsonl"
    audit_path = args.output_dir / "silver-audit.jsonl"

    stats = {
        "conversations": 0,
        "usable_conversations": 0,
        "teacher_claims": 0,
        "kept_claims": 0,
        "dropped_claims": 0,
        "repairs": 0,
    }
    drop_reasons: dict[str, int] = {}

    with httpx.Client() as client, train_path.open("w", encoding="utf-8") as train_handle, audit_path.open(
        "w", encoding="utf-8"
    ) as audit_handle:
        for index, row in enumerate(rows, start=1):
            conversation = row["conversation"]
            user_text, assistant_text, dates = split_conversation(conversation)
            reference = latest_date(dates)
            stats["conversations"] += 1
            try:
                raw, latency, payload = bench.call_model(
                    client,
                    args.teacher,
                    conversation,
                    timeout=args.timeout,
                    num_ctx=args.num_ctx,
                    num_predict=args.num_predict,
                )
                claims, parse_error = bench.parse_claims(raw)
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                claims, parse_error, raw, latency, payload = [], f"{type(exc).__name__}: {exc}", "", 0.0, {}

            stats["teacher_claims"] += len(claims)
            kept, dropped, repairs = validate_and_repair(
                conversation,
                user_text,
                assistant_text,
                reference,
                claims,
            )
            stats["kept_claims"] += len(kept)
            stats["dropped_claims"] += len(dropped)
            stats["repairs"] += len(repairs)
            for item in dropped:
                reason = str(item["reason"]).split(":")[0]
                drop_reasons[reason] = drop_reasons.get(reason, 0) + 1

            if kept and not parse_error:
                stats["usable_conversations"] += 1
                train_handle.write(
                    json.dumps(
                        {
                            "conversation_id": row.get("conversation_id"),
                            "difficulty": row.get("difficulty"),
                            "messages": [
                                {"role": "system", "content": bench.SYSTEM_PROMPT},
                                {"role": "user", "content": conversation},
                                {
                                    "role": "assistant",
                                    "content": json.dumps({"claims": kept}, ensure_ascii=False),
                                },
                            ],
                            "claim_count": len(kept),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                train_handle.flush()

            audit_handle.write(
                json.dumps(
                    {
                        "conversation_id": row.get("conversation_id"),
                        "parse_error": parse_error,
                        "reference_date": reference.isoformat() if reference else None,
                        "teacher_claims": claims,
                        "kept_claims": kept,
                        "dropped": dropped,
                        "repairs": repairs,
                        "latency_ms": round(latency, 2),
                        "done_reason": payload.get("done_reason"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            audit_handle.flush()
            print(
                f"{index:03d}/{len(rows):03d} {row.get('conversation_id')} "
                f"teacher={len(claims)} kept={len(kept)} dropped={len(dropped)} repairs={len(repairs)} "
                f"{latency:.0f}ms",
                flush=True,
            )

    report = {
        "teacher": args.teacher,
        "dataset": str(args.dataset),
        "stats": stats,
        "drop_reasons": dict(sorted(drop_reasons.items(), key=lambda item: -item[1])),
        "train_path": str(train_path),
        "audit_path": str(audit_path),
    }
    (args.output_dir / "silver-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
