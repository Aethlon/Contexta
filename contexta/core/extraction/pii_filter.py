"""Pure-code PII detection and redaction for the Contexta memory engine.

Extends the credential coverage in :mod:`contexta.core.extraction.sensitive_filter`
to personal data. Nothing in this module calls a model: every finding comes from a
regular expression plus, where a false positive would be expensive, a checksum
validator (Luhn, ISO 7064 mod-97, ABA weighting, IPv4 octet ranges, SSN issuance
rules). That keeps the redaction path deterministic, auditable and offline.

Two tiers, because blanket deletion would destroy the memory engine:

``direct``
    Identifiers with no value to a long-term memory: credentials, contact details,
    government and financial numbers, precise location, health facts. Replaced with
    ``[REDACTED]``.

``soft``
    Identity that the entity graph *needs* in order to link memories across
    sessions (person, organisation, city). Erased content would break coreference,
    so these are replaced with a stable pseudonym such as ``[PERSON_1]``. The same
    value always maps to the same token within a scan, and standalone first-name
    mentions are backfilled, so "Priya Raman ... Priya said ..." stays one node.
    The real name is never written to storage.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

REDACTED = "[REDACTED]"

TIER_DIRECT = "direct"
TIER_SOFT = "soft"

_PSEUDONYM_PREFIX = {
    "person_name": "PERSON",
    "organization": "ORG",
    "location": "LOCATION",
}


@dataclass(frozen=True)
class PiiFinding:
    """A single detected value, located in the source text."""

    category: str
    tier: str
    start: int
    end: int
    value: str
    validated: bool = False

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass
class PiiScanResult:
    """Outcome of a PII scan."""

    redacted_content: str
    findings: list[PiiFinding] = field(default_factory=list)
    pseudonym_map: dict[str, str] = field(default_factory=dict)

    @property
    def contains_pii(self) -> bool:
        return bool(self.findings)

    def categories(self) -> set[str]:
        return {finding.category for finding in self.findings}


# --------------------------------------------------------------------------- #
# Checksum / shape validators. These are what keep precision high.
# --------------------------------------------------------------------------- #


def _luhn_valid(digits: str) -> bool:
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        return False
    total = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        value = int(char)
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _iban_valid(canonical: str) -> bool:
    """ISO 13616 mod-97 check on the compact form."""
    compact = re.sub(r"\s+", "", canonical).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", compact):
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(str(ord(char) - 55) if char.isalpha() else char for char in rearranged)
    return int(numeric) % 97 == 1


def _aba_routing_valid(digits: str) -> bool:
    """ABA routing numbers satisfy the 3-7-1 weighted checksum.

    The weight applies to positions 1,4,7 (three), 2,5,8 (seven) and 3,6,9 (one),
    so the weight tuple has to span the whole number rather than just the first
    three digits.
    """
    if len(digits) != 9 or not digits.isdigit():
        return False
    weights = (3, 7, 1, 3, 7, 1, 3, 7, 1)
    total = sum(int(char) * weight for char, weight in zip(digits, weights, strict=True))
    return total % 10 == 0


def _ipv4_valid(text: str) -> bool:
    parts = text.split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        if not part.isdigit() or len(part) > 3:
            return False
        if not 0 <= int(part) <= 255:
            return False
        if len(part) > 1 and part[0] == "0":
            return False
    return True


def _ssn_valid(text: str) -> bool:
    """Exclude the ranges the SSA never issues."""
    digits = re.sub(r"\D", "", text)
    if len(digits) != 9:
        return False
    area, group, serial = digits[:3], digits[3:5], digits[5:]
    if area in {"000", "666"} or area[0] == "9":
        return False
    return not (group == "00" or serial == "0000")


_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)

# A list of ~90 alternatives has to be joined into one regex alternation; an
# f-string here would interpolate the tuple repr instead of the terms.
_HEALTH_TERMS = "|".join((  # noqa: FLY002
    "type 1 diabetes", "type 2 diabetes", "diabetes mellitus", "hypertension",
    "major depressive disorder", "depression", "anxiety disorder", "generalized anxiety",
    "bipolar disorder", "schizophrenia", "psychosis", "epilepsy", "seizure disorder",
    "asthma", "copd", "emphysema", "hiv", "hepatitis b", "hepatitis c", "tuberculosis",
    "cancer", "carcinoma", "leukemia", "lymphoma", "melanoma", "multiple sclerosis",
    "parkinson", "alzheimers", "crohns disease", "ulcerative colitis", "celiac disease",
    "lupus", "psoriasis", "rheumatoid arthritis", "fibromyalgia", "anemia", "thalassemia",
    "kidney disease", "renal failure", "liver disease", "cirrhosis", "heart disease",
    "atrial fibrillation", "coronary artery disease", "angina", "stroke", "aneurysm",
    "pulmonary embolism", "deep vein thrombosis", "miscarriage", "stillbirth", "infertility",
    "pregnancy", "abortion", "contraceptive", "hiv positive", "std", "sti", "chlamydia",
    "gonorrhea", "syphilis", "herpes", "adhd", "autism", "schizotypal",
    "metformin", "insulin", "warfarin", "heparin", "lisinopril", "amlodipine",
    "atorvastatin", "simvastatin", "sertraline", "fluoxetine", "citalopram", "escitalopram",
    "paroxetine", "venlafaxine", "quetiapine", "risperidone", "olanzapine", "aripiprazole",
    "clozapine", "lithium", "valproate", "carbamazepine", "lamotrigine", "levetiracetam",
    "gabapentin", "pregabalin", "amoxicillin", "azithromycin", "ciprofloxacin",
    "levothyroxine", "methimazole", "prednisone", "prednisolone", "methylprednisolone",
    "adalimumab", "rituximab", "etanercept", "infliximab", "omeprazole", "pantoprazole",
    "salbutamol", "albuterol", "fluticasone", "montelukast", "apixaban", "rivaroxaban",
    "clopidogrel", "digoxin", "levodopa", "donepezil", "memantine", "sildenafil",
))

# Capitalised bigrams are the only reliable pure-code handle on bare person names,
# so the stoplist has to carry the vocabulary a memory engine actually sees.
_NAME_STOPWORDS = {
    "the", "a", "an", "this", "that", "these", "those", "it", "its", "we", "our", "us",
    "i", "my", "me", "you", "your", "he", "him", "his", "she", "her", "hers", "they",
    "them", "their", "if", "when", "while", "after", "before", "then", "than", "so",
    "because", "however", "although", "but", "and", "for", "with", "from", "into",
    "on", "at", "by", "to", "of", "in", "is", "are", "was", "were", "be", "been",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "mon", "tue", "wed", "thu", "fri", "sat", "sun", "january", "february", "march",
    "april", "may", "june", "july", "august", "september", "october", "november",
    "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct",
    "nov", "dec", "server", "service", "client", "data", "memory", "retrieval",
    "pipeline", "vector", "model", "layer", "index", "cache", "queue", "table",
    "column", "row", "cell", "graph", "node", "edge", "token", "chunk", "batch",
    "worker", "error", "warning", "info", "debug", "trace", "health", "status",
    "version", "release", "sprint", "ticket", "issue", "bug", "feature", "story",
    "merge", "branch", "commit", "deploy", "build", "test", "unit", "integration",
    "smoke", "query", "schema", "migration", "backup", "restore", "alert", "metric",
    "dashboard", "report", "export", "import", "upload", "download", "config",
    "setting", "option", "flag", "value", "name", "type", "class", "object", "method",
    "function", "field", "event", "message", "response", "request", "header", "cookie",
    "session", "password", "secret", "docker", "kubernetes", "postgres", "python",
    "javascript", "typescript", "react", "nginx", "redis", "kafka", "linux", "windows",
    "morning", "evening", "night", "today", "tomorrow", "yesterday", "week",
    "month", "year", "day", "time", "date", "number", "count", "total", "average",
    "first", "second", "third", "last", "next", "new", "old", "good", "bad", "high",
    "low", "north", "south", "east", "west", "left", "right", "up", "down", "over",
    "under", "out", "off", "again", "once", "here", "there", "all", "any", "some",
    "each", "more", "most", "other", "same", "such", "only", "own", "too", "very",
    "team", "office", "company", "project", "product", "customer", "user", "users",
    "requests", "responses", "memories", "context",
    "prompt", "system", "assistant", "agent", "tool", "tools", "file", "files",
    "line", "lines", "page", "pages", "note", "notes", "task", "tasks", "job", "jobs",
}

_ORG_SUFFIXES = (
    "Inc", "Inc\\.", "LLC", "L\\.L\\.C\\.", "Ltd", "Ltd\\.", "Corp", "Corp\\.",
    "Corporation", "Company", "Co\\.", "GmbH", "LLP", "PLC", "S\\.A\\.", "AG", "B\\.V\\.",
)

_ADDRESS_SUFFIXES = (
    "Street", "St", "Avenue", "Ave", "Road", "Rd", "Lane", "Ln", "Drive", "Dr",
    "Boulevard", "Blvd", "Court", "Ct", "Terrace", "Ter", "Place", "Pl", "Square",
    "Sq", "Way", "Highway", "Hwy", "Circle", "Cir", "Parkway", "Pwy", "Row", "Close",
)

# f-string interpolation renders a tuple as its repr, so alternations are joined
# explicitly rather than interpolated directly into the pattern.
_ORG_SUFFIX_RE = "|".join(_ORG_SUFFIXES)
_ADDRESS_SUFFIX_RE = "|".join(_ADDRESS_SUFFIXES)

# Triggers are matched case-insensitively while the captured name must stay
# case-sensitive, hence the scoped (?i:...) groups.
_NAME_TRIGGER = r"(?i:my name is|i am|i'm|im|this is|call me|signing as)"
_HONORIFIC_TRIGGER = r"(?i:mr|mrs|ms|miss|dr|prof|sir|madam)"


class PiiFilter:
    """Deterministic, model-free PII detector and redactor."""

    def __init__(self, *, pseudonymize: bool = True) -> None:
        self.pseudonymize = pseudonymize
        self._direct = self._compile_direct()
        self._soft = self._compile_soft()

    # -- pattern registry ------------------------------------------------- #

    def _compile_direct(self) -> list[tuple[str, re.Pattern[str], bool]]:
        """(category, pattern, needs_validator) for the direct tier."""
        specs: list[tuple[str, str, bool]] = [
            # --- credentials the secret filter does not cover -------------
            ("aws_secret_key",
             r"(?i)aws_secret_access_key\s*[=:]\s*[\"']?([A-Za-z0-9/+=]{40})[\"']?", True),
            ("slack_token", r"\b(xox[baprs]-[A-Za-z0-9\-]{10,})\b", True),
            ("sendgrid_key", r"\b(SG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,})\b", True),
            ("npm_token", r"\b(npm_[A-Za-z0-9]{30,})\b", True),
            ("url_credentials",
             r"\b([a-z][a-z0-9+.\-]*://)([^\s:/@]+):([^\s@/]+)@", True),
            ("private_key",
             r"(-----BEGIN [A-Z ]*PRIVATE KEY-----\s*)([A-Za-z0-9+/=\s]{16,})", True),
            ("openai_key", r"\b(sk-proj-[A-Za-z0-9_\-]{20,})\b", True),

            # --- contact ----------------------------------------------------
            ("email",
             (r"\b([A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
              r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,})\b"), True),
            ("email",
             (r"\b([A-Za-z0-9._%+\-]+\s?\[(?:at|@)\]\s?[A-Za-z0-9.\-]+\s?"
              r"\[(?:dot|\.)\]\s?[A-Za-z]{2,})\b"), True),
            # \b cannot precede "(" (both sides are non-word), so the phone shapes
            # use digit lookarounds instead of word boundaries. Every pattern must
            # expose group 1 as the value to erase.
            ("phone",
             r"((?<!\d)\(\d{3}\)\s?\d{3}[\s.\-]\d{4}(?!\d))", True),
            ("phone",
             r"((?<!\d)\d{3}[\s.\-]\d{3}[\s.\-]\d{4}(?!\d))", True),
            ("phone",
             (r"((?<![\d+])\+\d{1,3}[\s.\-]?\(?\d{1,4}\)?[\s.\-]?\d{2,4}"
              r"[\s.\-]?\d{2,4}(?:[\s.\-]?\d{1,4})?(?!\d))"), True),
            ("phone",
             (r"(?i)\b(?:phone|mobile|cell|telephone|tel|whatsapp|contact\s+number)\s*"
              r"(?:number|no\.?|#)?\s*(?:is|:|=)?\s*(\+?\d[\d\s\-().]{6,18}\d)"), True),

            # --- government identity ---------------------------------------
            ("national_id", r"\b(\d{3}-\d{2}-\d{4})\b", _ssn_valid),
            ("national_id", r"\b(\d{4}\s\d{4}\s\d{4})\b", True),
            ("national_id", r"\b(\d{2}-\d{7})\b", True),
            ("national_id",
             (r"\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
              r"[0-9a-fA-F]{12})\b"), True),
            ("passport",
             r"(?i)\bpassport\s*(?:number|no\.?|#)?\s*[:=]?\s*([A-Z]{1,2}\d{6,9})\b", True),
            ("drivers_license",
             (r"(?i)(?:\bdriver'?s?\s*licen[cs]e|driving\s*licen[cs]e|\bdl\b)"
              r"\s*(?:number|no\.?|#)?\s*[:=]?\s*([A-Z]{0,2}\d{5,12})\b"), True),

            # --- finance ----------------------------------------------------
            ("payment_card", r"\b((?:\d[ \-]?){12,18}\d)\b", _luhn_valid),
            ("bank_account",
             r"\b([A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?)\b",
             _iban_valid),
            ("bank_account", r"\b(\d{9})\b", _aba_routing_valid),
            ("bank_account",
             r"(?i)\baccount\s*(?:number|no\.?|#)?\s*[:=]?\s*(\d{6,17})\b", True),

            # --- date of birth ---------------------------------------------
            # "born" is a strong signal on its own; the "on" is optional because
            # extracted memories paraphrase ("born 1985-07-14").
            ("date_of_birth",
             (r"(?i)\b(?:date\s+of\s+birth|birth\s*date|d\.?o\.?b\.?|born(?:\s+on)?)\b"
              r"[^.\n]{0,24}?(\d{4}-\d{2}-\d{2})"), True),
            ("date_of_birth",
             (rf"(?i)\b(?:date\s+of\s+birth|birth\s*date|d\.?o\.?b\.?|born(?:\s+on)?)\b"
              rf"[^.\n]{{0,24}}?(\d{{1,2}}\s+(?:{_MONTHS})\s+\d{{4}})"), True),

            # --- location / device identity ---------------------------------
            ("postal_address",
             (rf"\b(\d{{1,6}}\s+(?:[A-Z][A-Za-z.'-]*\s+){{0,4}}(?:{_ADDRESS_SUFFIX_RE})\b"
              r"(?:\s*,?\s*(?:Apt|Apartment|Unit|Suite|Ste|Floor|Fl)\.?\s*[A-Za-z0-9\-]+)?)"),
             True),
            ("postal_address", r"\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b", True),
            ("network_identifier", r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", _ipv4_valid),
            ("network_identifier", r"\b([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\b", True),
            ("precise_location",
             r"\b(-?\d{1,2}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,})\b", True),

            # --- health -----------------------------------------------------
            ("health_data", rf"(?i)\b((?:{_HEALTH_TERMS}))\b", True),
        ]

        compiled: list[tuple[str, re.Pattern[str], bool]] = []
        for category, pattern, validator in specs:
            compiled.append((category, re.compile(pattern), validator))
        return compiled

    def _compile_soft(self) -> list[tuple[str, re.Pattern[str]]]:
        return [
            ("person_name",
             re.compile(rf"\b{_HONORIFIC_TRIGGER}\.?\s+"
                        r"([A-Z][a-z]{1,15}(?:\s+[A-Z][a-z]{1,15}){1,2})\b")),
            ("person_name",
             re.compile(rf"\b{_NAME_TRIGGER}\s+"
                        r"([A-Z][a-z]{1,15}(?:\s+[A-Z][a-z]{1,15}){1,2})\b")),
            ("person_name",
             re.compile(r"\b(([A-Z][a-z]{1,15})\s+([A-Z][a-z]{1,15}))\b")),
            ("organization",
             re.compile(r"\b([A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*){0,3}"
                        rf"\s+(?:{_ORG_SUFFIX_RE}))\b")),
            ("location",
             re.compile(r"\b([A-Z][a-z]{2,20}(?:[ \-][A-Z][a-z]{2,20})?),\s*"
                        r"([A-Z]{2})\b")),
        ]

    # -- validation helpers ----------------------------------------------- #

    @staticmethod
    def _phone_plausible(raw: str) -> bool:
        digits = re.sub(r"\D", "", raw)
        if not 7 <= len(digits) <= 15:
            return False
        return re.fullmatch(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})+", raw.strip()) is None

    @staticmethod
    def _soft_name_ok(candidate: str) -> bool:
        words = candidate.split()
        if len(words) < 2:
            return False
        for word in words:
            if word.lower() in _NAME_STOPWORDS:
                return False
            if word.isupper():
                return False
        return True

    @staticmethod
    def _soft_location_ok(match: re.Match[str]) -> bool:
        return match.group(2).upper() in _US_STATES

    # -- scanning ---------------------------------------------------------- #

    def _scan_direct(self, content: str) -> list[PiiFinding]:
        findings: list[PiiFinding] = []
        for category, pattern, validator in self._direct:
            for match in pattern.finditer(content):
                group = match.lastindex or 1
                try:
                    value = match.group(group)
                except (IndexError, re.error):
                    # A pattern without a capture group would silently disable
                    # itself, so surface it instead of skipping the match.
                    logger.warning(
                        "PII pattern for %s exposes no capture group; skipping match",
                        category,
                    )
                    continue
                if value is None:
                    continue
                start = match.start(group)
                if callable(validator):
                    ok = bool(validator(value))
                    validated = True
                else:
                    # `True` marks a shape that is unambiguous on its own.
                    ok = True
                    if category == "phone" and not self._phone_plausible(value):
                        ok = False
                    validated = False
                if not ok:
                    continue
                findings.append(
                    PiiFinding(
                        category=category,
                        tier=TIER_DIRECT,
                        start=start,
                        end=start + len(value),
                        value=value,
                        validated=validated,
                    )
                )
        return findings

    def _scan_soft(self, content: str) -> list[PiiFinding]:
        findings: list[PiiFinding] = []
        for category, pattern in self._soft:
            for match in pattern.finditer(content):
                if category == "location":
                    if not self._soft_location_ok(match):
                        continue
                    start, end = match.span()
                elif category == "organization":
                    start, end = match.span(1)
                else:
                    candidate = match.group(1) if match.lastindex else match.group(0)
                    if not self._soft_name_ok(candidate):
                        continue
                    start = match.start(1) if match.lastindex else match.start(0)
                    end = match.end(1) if match.lastindex else match.end(0)
                findings.append(
                    PiiFinding(
                        category=category,
                        tier=TIER_SOFT,
                        start=start,
                        end=end,
                        value=content[start:end],
                        validated=False,
                    )
                )
        return findings

    @staticmethod
    def _resolve_overlaps(findings: list[PiiFinding]) -> list[PiiFinding]:
        """Drop lower-priority findings that overlap a higher-priority span.

        Direct tier always wins over soft. Within a tier the longer span wins, which
        is what stops "Cobalt Systems LLC" being read as a person called
        "Cobalt Systems".
        """
        tier_rank = {TIER_DIRECT: 0, TIER_SOFT: 1}
        ordered = sorted(
            findings,
            key=lambda f: (tier_rank.get(f.tier, 9), -f.length, f.start),
        )
        accepted: list[PiiFinding] = []
        for candidate in ordered:
            clash = any(
                candidate.start < other.end and other.start < candidate.end
                for other in accepted
            )
            if not clash:
                accepted.append(candidate)
        return sorted(accepted, key=lambda f: f.start)

    # -- public API -------------------------------------------------------- #

    def scan(self, content: str) -> PiiScanResult:
        """Detect and redact PII, pseudonymising soft identifiers consistently."""
        if not content:
            return PiiScanResult(redacted_content=content)

        direct = self._resolve_overlaps(self._scan_direct(content))
        soft = self._resolve_overlaps(self._scan_soft(content))

        # Drop soft findings that sit inside a span already redacted as direct.
        soft = [
            finding
            for finding in soft
            if not any(f.start < finding.end and finding.start < f.end for f in direct)
        ]

        # Direct tier: offset-based replacement, applied right to left.
        redacted = content
        for finding in sorted(direct, key=lambda f: f.start, reverse=True):
            redacted = redacted[: finding.start] + REDACTED + redacted[finding.end :]

        # Soft tier: assign stable tokens, then literal replacement so that later
        # mentions of the same name collapse onto the same pseudonym.
        pseudonym_map: dict[str, str] = {}
        if self.pseudonymize:
            counters: dict[str, int] = {}
            for finding in soft:
                prefix = _PSEUDONYM_PREFIX.get(finding.category, "ENTITY")
                key = finding.value.strip().casefold()
                if key not in pseudonym_map:
                    counters[prefix] = counters.get(prefix, 0) + 1
                    pseudonym_map[key] = f"[{prefix}_{counters[prefix]}]"

            # Given name and surname are backfilled onto the same token so that
            # "Priya Raman ... Priya said ..." stays a single graph node instead of
            # leaving a bare surname behind.
            substitutions: list[tuple[str, str]] = []
            for finding in soft:
                token = pseudonym_map.get(finding.value.strip().casefold())
                if not token:
                    continue
                candidates = [finding.value]
                if finding.category == "person_name":
                    parts = finding.value.split()
                    candidates.extend(part for part in parts[1:] if len(part) >= 3)
                    candidates.extend(part for part in parts[:1] if len(part) >= 3)
                for candidate in candidates:
                    substitutions.append((candidate, token))

            seen: set[str] = set()
            for value, token in sorted(substitutions, key=lambda pair: -len(pair[0])):
                if value.casefold() in seen:
                    continue
                seen.add(value.casefold())
                redacted = re.sub(
                    rf"(?<![A-Za-z0-9]){re.escape(value)}(?![A-Za-z0-9])",
                    token,
                    redacted,
                )
        else:
            for finding in sorted(soft, key=lambda f: f.start, reverse=True):
                redacted = redacted[: finding.start] + REDACTED + redacted[finding.end :]

        return PiiScanResult(
            redacted_content=redacted,
            findings=sorted(direct + soft, key=lambda f: f.start),
            pseudonym_map=pseudonym_map,
        )

    def contains_pii(self, content: str) -> bool:
        return self.scan(content).contains_pii
