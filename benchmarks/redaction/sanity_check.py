"""Sanity-check the production gate end to end, without a database."""

from contexta.core.extraction.sensitive_filter import primary_scan, secondary_redact
from contexta.core.schemas import ExtractedMemory, MemoryType, SourceType

AWS_AKID = "AKIA" "IOSFODNN7EXAMPLE"

observation = (
    "Hi, I'm Dana Whitfield (dana.whitfield@northwind-logistics.com, +1 415-555-0132). "
    f"Our card on file is 4111 1111 1111 1111 and the AWS key {AWS_AKID} is in env. "
    "I was born on 1985-07-14 and we moved our office to 4521 Nagle Street, Portland. "
    "I have type 2 diabetes and take metformin daily. "
    "Non-sensitive context: the retrieval pipeline shipped build 18422 on 2026-01-15."
)

scan = primary_scan(observation)
print("REDACTED OBSERVATION:")
print(" ", scan.redacted_content)
print()
print("events:", len(scan.redaction_events), "| pseudonyms:", scan.pseudonym_map)
print("categories:", sorted({f.category for f in scan.pii_findings}))

memory = ExtractedMemory(
    memory_type=MemoryType.FACT,
    source_type=SourceType.USER_EXPLICIT,
    title="Contact details",
    content="The user is Dana Whitfield, reachable at dana.whitfield@northwind-logistics.com, "
            "born 1985-07-14, card 4111 1111 1111 1111, treated for type 2 diabetes.",
)
discard, cleaned = secondary_redact(memory.content)
print()
print("SECONDARY GATE -> discard:", discard)
print("  cleaned:", cleaned)

safe = ExtractedMemory(
    memory_type=MemoryType.FACT,
    source_type=SourceType.USER_EXPLICIT,
    title="Build",
    content="The retrieval pipeline shipped build 18422 on 2026-01-15.",
)
discard2, cleaned2 = secondary_redact(safe.content)
print()
print("benign memory -> discard:", discard2, "| unchanged:", cleaned2 == safe.content)

memory.content = cleaned
print("assignment to ExtractedMemory.content works:", memory.content[:60], "...")

