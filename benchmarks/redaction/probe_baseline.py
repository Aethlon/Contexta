"""Quick probe: measure current production redaction against the PII corpus."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "contexta" / "core" / "extraction"))
sys.path.insert(0, str(Path(__file__).parent))

from benchmarks.redaction.corpus import CASES
from contexta.core.extraction.sensitive_filter import SensitiveDataFilter

f = SensitiveDataFilter()
stats: dict[str, list[int]] = {}
leaks = []
fps = []

for case in CASES:
    tier = case["tier"]
    out = f.scan_and_redact(case["text"]).redacted_content
    leaked = [s for s in case["must_not_contain"] if s in out]
    s = stats.setdefault(tier, [0, 0])
    s[1] += 1
    if not leaked:
        s[0] += 1
    else:
        leaks.append((case["case_id"], case["category"], leaked))
    for keep in case.get("must_preserve", []):
        if keep not in out:
            fps.append((case["case_id"], keep, out))

print("=== CURRENT production SensitiveDataFilter (secrets only) ===")
for tier, (ok, total) in sorted(stats.items()):
    print(f"  {tier:8s} {ok}/{total} clean")
print(f"\nLEAKS ({len(leaks)}):")
for cid, cat, leaked in leaks:
    print(f"  {cid:26s} {cat:20s} {leaked}")
print(f"\nFALSE POSITIVES on benign ({len(fps)}):")
for cid, keep, out in fps:
    print(f"  {cid:26s} lost {keep!r} -> {out!r}")
