"""Benchmark the pure-code redaction gate: ingest -> redact -> extract -> store.

Runs the labeled corpus in :mod:`benchmarks.redaction.corpus` through the real
production entry point (``primary_scan``) and, optionally, through the fine-tuned
extractor so the report can assert on what would actually be persisted rather than
only on the redacted string.

Writes three artifacts to ``benchmarks/redaction/reports``:

* ``redaction_results.csv``   one row per case, flat, for spreadsheets
* ``redaction_results.json``  full report including aggregates and baseline delta
* ``redaction_report.html``   self-contained visual report

Usage:
    uv run --no-sync python benchmarks/redaction/run_redaction_test.py
    uv run --no-sync python benchmarks/redaction/run_redaction_test.py --extract
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "benchmarks" / "extraction"))

from benchmarks.redaction.corpus import CASES
from contexta.core.extraction.sensitive_filter import (
    SensitiveDataFilter,
    primary_scan,
)

REPORT_DIR = REPO_ROOT / "benchmarks" / "redaction" / "reports"
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "contexta-lfm-extract"


def _leaks(case: dict[str, Any], text: str) -> list[str]:
    return [value for value in case["must_not_contain"] if value in text]


def _lost(case: dict[str, Any], text: str) -> list[str]:
    return [value for value in case.get("must_preserve", []) if value not in text]


def _redact_baseline(text: str) -> str:
    return SensitiveDataFilter().scan_and_redact(text).redacted_content


def run_extraction_leg(cases: list[dict[str, Any]], redacted_texts: dict[str, str]) -> list[dict[str, Any]]:
    """Send redacted text to the fine-tuned extractor and audit what it proposes.

    This is the leg that matters for the storage guarantee: the model only ever
    sees redacted input, so anything it emits is a candidate memory row.
    """
    import httpx
    from contract import SYSTEM_PROMPT, parse_memories

    rows: list[dict[str, Any]] = []
    with httpx.Client(timeout=180.0) as client:
        for case in cases:
            text = redacted_texts[case["case_id"]]
            prompt = (
                f"{SYSTEM_PROMPT}\n\n"
                f"Conversation:\nuser: {text}\n\n"
                "Return the memories array as JSON."
            )
            record: dict[str, Any] = {
                "case_id": case["case_id"],
                "category": case["category"],
                "memories": 0,
                "parse_ok": False,
                "leaked_into_memory": [],
                "sample": "",
            }
            try:
                response = client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.0, "num_predict": 512},
                    },
                )
                response.raise_for_status()
                raw = response.json().get("response", "")
                memories, _ = parse_memories(raw)
                record["parse_ok"] = True
                record["memories"] = len(memories)
                blob = " ".join(
                    f"{m.get('text', '')} {m.get('subject', '')} "
                    f"{m.get('object', '')}"
                    for m in memories
                )
                record["sample"] = blob[:400]
                record["leaked_into_memory"] = _leaks(case, blob)
            except Exception as exc:  # noqa: BLE001 - a dead extractor must not abort the report
                record["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(record)
    return rows


def evaluate_cases() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run every case through both the new gate and the legacy credential filter."""
    rows: list[dict[str, Any]] = []
    redacted_texts: dict[str, str] = {}

    for case in CASES:
        result = primary_scan(case["text"])
        redacted = result.redacted_content
        redacted_texts[case["case_id"]] = redacted

        leaks = _leaks(case, redacted)
        lost = _lost(case, redacted)
        baseline_leaks = _leaks(case, _redact_baseline(case["text"]))
        idempotent = primary_scan(redacted).redacted_content == redacted
        residual = primary_scan(redacted)

        tiers = Counter(finding.tier for finding in result.pii_findings)
        categories = sorted({finding.category for finding in result.pii_findings})

        rows.append(
            {
                "case_id": case["case_id"],
                "tier": case["tier"],
                "category": case["category"],
                "input": case["text"],
                "redacted": redacted,
                "leaked_values": leaks,
                "leak_count": len(leaks),
                "lost_values": lost,
                "false_positive": bool(lost),
                "redactions": len(result.redaction_events),
                "direct_hits": tiers.get("direct", 0),
                "soft_hits": tiers.get("soft", 0),
                "detected_categories": ",".join(categories),
                "validator_backed": sum(1 for f in result.pii_findings if f.validated),
                "pseudonyms": len(result.pseudonym_map),
                "idempotent": idempotent,
                "residual_findings": len(residual.pii_findings),
                "status": _status(case, leaks, lost),
                "baseline_leak_count": len(baseline_leaks),
                "baseline_leaked_values": baseline_leaks,
            }
        )
    return rows, [redacted_texts]


def _status(case: dict[str, Any], leaks: list[str], lost: list[str]) -> str:
    if case["tier"] == "benign":
        if lost:
            return "false_positive"
        return "pass"
    if leaks:
        return "leak"
    if lost:
        return "redacted_but_brittle"
    return "pass"


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_tier: dict[str, dict[str, Any]] = {}
    for tier in ("direct", "soft", "benign"):
        subset = [r for r in rows if r["tier"] == tier]
        if not subset:
            continue
        if tier == "benign":
            clean = sum(1 for r in subset if not r["false_positive"])
            by_tier[tier] = {
                "cases": len(subset),
                "passed": clean,
                "failed": len(subset) - clean,
                "rate": round(clean / len(subset), 4),
                "metric": "specificity (no over-redaction)",
            }
        else:
            clean = sum(1 for r in subset if r["status"] == "pass")
            by_tier[tier] = {
                "cases": len(subset),
                "passed": clean,
                "failed": len(subset) - clean,
                "rate": round(clean / len(subset), 4),
                "metric": "recall (nothing leaked)",
            }

    by_category: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["category"]].append(row)
    for category, subset in sorted(grouped.items()):
        if subset[0]["tier"] == "benign":
            ok = sum(1 for r in subset if not r["false_positive"])
        else:
            ok = sum(1 for r in subset if r["status"] == "pass")
        by_category[category] = {
            "cases": len(subset),
            "passed": ok,
            "failed": len(subset) - ok,
            "rate": round(ok / len(subset), 4),
            "tier": subset[0]["tier"],
        }

    return {
        "by_tier": by_tier,
        "by_category": by_category,
        "totals": {
            "cases": len(rows),
            "leaks": sum(1 for r in rows if r["status"] == "leak"),
            "false_positives": sum(1 for r in rows if r["false_positive"]),
            "idempotent": sum(1 for r in rows if r["idempotent"]),
            "baseline_leaks": sum(r["baseline_leak_count"] for r in rows),
            "redactions": sum(r["redactions"] for r in rows),
        },
    }


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    columns = [
        "case_id", "tier", "category", "status", "leak_count", "false_positive",
        "redactions", "direct_hits", "soft_hits", "validator_backed", "pseudonyms",
        "idempotent", "residual_findings", "detected_categories",
        "baseline_leak_count", "input", "redacted",
        "leaked_values", "lost_values",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            for key in ("leaked_values", "lost_values", "baseline_leaked_values"):
                flat[key] = " | ".join(flat.get(key, []))
            writer.writerow({key: flat.get(key, "") for key in columns})


def write_json(report: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def write_html(report: dict[str, Any], path: Path) -> None:
    agg = report["aggregate"]
    totals = agg["totals"]
    rows = report["cases"]
    extraction = report.get("extraction", {})

    tier_rows = "".join(
        f"<tr><td><span class='tier tier-{key}'>{html.escape(key)}</span></td>"
        f"<td class='num'>{value['cases']}</td>"
        f"<td class='num'>{value['passed']}</td>"
        f"<td class='num {'bad' if value['failed'] else 'good'}'>{value['failed']}</td>"
        f"<td class='num'><div class='bar'><span style='width:{value['rate'] * 100:.0f}%'></span></div>"
        f"{_pct(value['rate'])}</td>"
        f"<td class='muted'>{html.escape(value['metric'])}</td></tr>"
        for key, value in agg["by_tier"].items()
    )

    cat_rows = "".join(
        f"<tr><td>{html.escape(category)}</td>"
        f"<td><span class='tier tier-{value['tier']}'>{value['tier']}</span></td>"
        f"<td class='num'>{value['cases']}</td>"
        f"<td class='num'>{value['passed']}</td>"
        f"<td class='num {'bad' if value['failed'] else 'good'}'>{value['failed']}</td>"
        f"<td class='num'>{_pct(value['rate'])}</td></tr>"
        for category, value in agg["by_category"].items()
    )

    def case_row(row: dict[str, Any]) -> str:
        status_class = {"pass": "good", "leak": "bad", "false_positive": "warn"}.get(
            row["status"], "warn"
        )
        leaked = " | ".join(row["leaked_values"]) or "—"
        lost = " | ".join(row["lost_values"]) or "—"
        return (
            f"<tr class='{status_class}'>"
            f"<td class='mono'>{html.escape(row['case_id'])}</td>"
            f"<td><span class='tier tier-{row['tier']}'>{row['tier']}</span></td>"
            f"<td>{html.escape(row['category'])}</td>"
            f"<td class='status'>{row['status']}</td>"
            f"<td class='num'>{row['leak_count']}</td>"
            f"<td class='num'>{row['redactions']}</td>"
            f"<td class='num'>{'yes' if row['idempotent'] else 'NO'}</td>"
            f"<td class='leak'>{html.escape(leaked)}</td>"
            f"<td class='muted'>{html.escape(lost)}</td>"
            f"<td class='sample'>{html.escape(row['redacted'][:220])}</td>"
            "</tr>"
        )

    body_rows = "".join(case_row(row) for row in rows)

    extraction_block = ""
    if extraction.get("ran"):
        leaked = extraction["cases_with_leak"]
        extraction_block = f"""
        <div class="card">
          <h2>3. Extraction &rarr; storage leg</h2>
          <p class="muted">Redacted text was sent to <code>{html.escape(extraction['model'])}</code>;
             every memory the model proposed was audited against the ground-truth PII list.</p>
          <div class="kpis">
            <div class="kpi"><div class="kpi-value">{extraction['cases']}</div><div class="kpi-label">cases extracted</div></div>
            <div class="kpi"><div class="kpi-value">{extraction['memories']}</div><div class="kpi-label">candidate memories</div></div>
            <div class="kpi {'bad' if leaked else 'good'}"><div class="kpi-value">{leaked}</div><div class="kpi-label">memories leaking PII</div></div>
          </div>
        </div>"""

    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Contexta redaction verification</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:32px; background:#0b0e14; color:#e6e9ef;
         font:14px/1.55 ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif; }}
  h1 {{ font-size:22px; margin:0 0 4px; }}
  h2 {{ font-size:15px; margin:0 0 12px; text-transform:uppercase;
        letter-spacing:.08em; color:#8b93a7; }}
  .sub {{ color:#8b93a7; margin:0 0 24px; }}
  .card {{ background:#121722; border:1px solid #1f2634; border-radius:10px;
           padding:20px; margin-bottom:20px; }}
  .kpis {{ display:flex; gap:14px; flex-wrap:wrap; margin:16px 0 4px; }}
  .kpi {{ background:#0e131c; border:1px solid #1f2634; border-radius:8px;
          padding:14px 18px; min-width:130px; }}
  .kpi-value {{ font-size:26px; font-weight:600; }}
  .kpi-label {{ color:#8b93a7; font-size:11px; text-transform:uppercase;
                letter-spacing:.06em; margin-top:2px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ text-align:left; color:#8b93a7; font-weight:500; font-size:11px;
        text-transform:uppercase; letter-spacing:.06em; padding:8px 10px;
        border-bottom:1px solid #1f2634; }}
  td {{ padding:8px 10px; border-bottom:1px solid #161b26; vertical-align:top; }}
  tr.pass td.status {{ color:#3fb950; }}
  tr.leak td.status {{ color:#f85149; }}
  tr.false_positive td.status {{ color:#d29922; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }}
  .muted {{ color:#8b93a7; }}
  .leak {{ color:#f85149; font-family:ui-monospace,Menlo,monospace; font-size:11px; }}
  .good {{ color:#3fb950; }} .bad {{ color:#f85149; }} .warn {{ color:#d29922; }}
  .sample {{ color:#9aa4b8; font-size:11.5px; max-width:380px; }}
  .status {{ font-weight:600; }}
  .tier {{ display:inline-block; padding:1px 7px; border-radius:20px;
           font-size:10.5px; text-transform:uppercase; letter-spacing:.05em; }}
  .tier-direct {{ background:#3d1d1d; color:#f85149; }}
  .tier-soft {{ background:#1d2b3d; color:#58a6ff; }}
  .tier-benign {{ background:#1d2f22; color:#3fb950; }}
  .bar {{ display:inline-block; width:70px; height:6px; background:#1f2634;
          border-radius:4px; margin-right:8px; vertical-align:middle; overflow:hidden; }}
  .bar span {{ display:block; height:100%; background:#3fb950; }}
  code {{ background:#0e131c; padding:1px 5px; border-radius:4px; font-size:12px; }}
</style></head><body>
<h1>Contexta &mdash; pure-code redaction verification</h1>
<p class="sub">Generated {html.escape(report['generated_at'])} &middot;
   deterministic regex + checksum validators, no model in the redaction path</p>

<div class="card">
  <h2>1. Headline</h2>
  <div class="kpis">
    <div class="kpi"><div class="kpi-value">{totals['cases']}</div><div class="kpi-label">cases</div></div>
    <div class="kpi {'good' if totals['leaks'] == 0 else 'bad'}"><div class="kpi-value">{totals['leaks']}</div><div class="kpi-label">PII leaks</div></div>
    <div class="kpi {'good' if totals['false_positives'] == 0 else 'warn'}"><div class="kpi-value">{totals['false_positives']}</div><div class="kpi-label">over-redactions</div></div>
    <div class="kpi"><div class="kpi-value">{totals['redactions']}</div><div class="kpi-label">values redacted</div></div>
    <div class="kpi"><div class="kpi-value">{totals['baseline_leaks']}</div><div class="kpi-label">leaks before this change</div></div>
  </div>
  <p class="muted">{totals['idempotent']}/{totals['cases']} cases are idempotent
     (a second pass finds nothing new).</p>
</div>

<div class="card">
  <h2>2. By tier</h2>
  <table><thead><tr><th>Tier</th><th class="num">Cases</th><th class="num">Pass</th>
  <th class="num">Fail</th><th class="num">Rate</th><th>Metric</th></tr></thead>
  <tbody>{tier_rows}</tbody></table>
  <h2 style="margin-top:22px">By category</h2>
  <table><thead><tr><th>Category</th><th>Tier</th><th class="num">Cases</th>
  <th class="num">Pass</th><th class="num">Fail</th><th class="num">Rate</th></tr></thead>
  <tbody>{cat_rows}</tbody></table>
</div>
{extraction_block}

<div class="card">
  <h2>4. Per-case detail</h2>
  <table><thead><tr><th>Case</th><th>Tier</th><th>Category</th><th>Status</th>
  <th class="num">Leaks</th><th class="num">Hits</th><th>Idempotent</th>
  <th>Leaked value</th><th>Over-redacted</th><th>Redacted output</th></tr></thead>
  <tbody>{body_rows}</tbody></table>
</div>
</body></html>"""
    path.write_text(document, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extract", action="store_true",
        help="also run the fine-tuned extractor over redacted text and audit memories",
    )
    args = parser.parse_args()

    rows, _ = evaluate_cases()
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "gate": "contexta.core.extraction.sensitive_filter.primary_scan",
        "model_free": True,
        "aggregate": aggregate(rows),
        "cases": rows,
    }

    if args.extract:
        redacted_map = {row["case_id"]: row["redacted"] for row in rows}
        extraction_rows = run_extraction_leg(CASES, redacted_map)
        report["extraction"] = {
            "ran": True,
            "model": OLLAMA_MODEL,
            "cases": len(extraction_rows),
            "memories": sum(r["memories"] for r in extraction_rows),
            "parse_failures": sum(1 for r in extraction_rows if not r["parse_ok"]),
            "cases_with_leak": sum(1 for r in extraction_rows if r["leaked_into_memory"]),
            "detail": extraction_rows,
        }
    else:
        report["extraction"] = {"ran": False}

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(rows, REPORT_DIR / "redaction_results.csv")
    write_json(report, REPORT_DIR / "redaction_results.json")
    write_html(report, REPORT_DIR / "redaction_report.html")

    totals = report["aggregate"]["totals"]
    print(f"cases={totals['cases']} leaks={totals['leaks']} "
          f"over_redactions={totals['false_positives']} "
          f"idempotent={totals['idempotent']}/{totals['cases']} "
          f"baseline_leaks={totals['baseline_leaks']}")
    for tier, value in report["aggregate"]["by_tier"].items():
        print(f"  {tier:7s} {value['passed']}/{value['cases']} ({_pct(value['rate'])})")
    if args.extract:
        ext = report["extraction"]
        print(f"  extraction: {ext['memories']} candidate memories, "
              f"{ext['cases_with_leak']} leaking PII")
    for row in rows:
        if row["status"] in {"leak", "false_positive"}:
            print(f"  [{row['status']}] {row['case_id']}: "
                  f"{row['leaked_values'] or row['lost_values']}")
    print(f"\nreports -> {REPORT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
