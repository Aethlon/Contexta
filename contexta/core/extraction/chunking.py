"""Chunked extraction for the fine-tuned extractor.

Why this exists
---------------
The extractor is a 1.2B fine-tune with a 128k context, so a long conversation
cannot run out of context. Measured against the real model, though, it quietly
loses facts long before any output budget is reached:

    facts in   single shot    chunked @10
    ---------  -------------  ------------
         30    24/30          30/30
         90    20/90          78/90

Both single-shot runs returned ``done_reason=stop`` — the model *chose* to stop,
it did not run out of tokens. So this is a compression failure, not an output
limit, and raising ``num_predict`` does not fix it. Splitting the conversation
into segments the model can hold all of does.

Chunk size 10 was measured, not guessed. Size 5 captured the same facts as 10 and
cost noticeably more wall time, so the default is the smallest size that
recovers full recall.

Two things make this safe rather than lossy:

* **Salvage.** If a chunk still truncates, ``salvage_json_array`` recovers every
  *complete* object from the truncated payload instead of discarding the whole
  response. A partial answer degrades to fewer facts, not to none.
* **Dedupe.** Chunks overlap in practice, so claims are merged on a normalised
  subject/predicate/object key and the first occurrence wins.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# Measured on the fine-tune. See the module docstring.
DEFAULT_CHUNK_SENTENCES = 10

# A chunk is also capped by characters, so one very long turn cannot become a
# single oversized chunk that reintroduces the original problem.
DEFAULT_MAX_CHUNK_CHARS = 1600

# If the whole conversation is already this small, do not chunk at all. Chunking
# short inputs measurably costs wall time and gains nothing.
MIN_CHUNK_SENTENCES = 2

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TURN_SPLIT = re.compile(r"^(user|assistant|system)\s*:\s*", re.IGNORECASE | re.MULTILINE)


@dataclass
class Chunk:
    """One segment of a conversation, with its turn prefix preserved."""

    text: str
    index: int
    total: int

    @property
    def is_only(self) -> bool:
        return self.total == 1


@dataclass
class ChunkedResult:
    """Aggregate outcome across every chunk, kept for telemetry and tests."""

    claims: list[dict[str, Any]] = field(default_factory=list)
    chunks: int = 0
    salvaged_chunks: int = 0
    failed_chunks: int = 0
    duplicate_claims: int = 0


def _normalise_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _hard_split(
    sentence: str,
    max_chars: int,
    role: str | None,
) -> list[tuple[str | None, str]]:
    """Break an over-long sentence on word boundaries.

    Only engages when a single unit exceeds the cap, which in practice means a
    long run with no sentence-ending punctuation. Returns ``[(role, text), ...]``.
    """
    if len(sentence) <= max_chars:
        return [(role, sentence)]

    pieces: list[tuple[str | None, str]] = []
    current: list[str] = []
    current_len = 0
    for word in sentence.split():
        # +1 for the joining space.
        if current and current_len + len(word) + 1 > max_chars:
            pieces.append((role, " ".join(current)))
            current = []
            current_len = 0
        current.append(word)
        current_len += len(word) + 1
    if current:
        pieces.append((role, " ".join(current)))
    return pieces or [(role, sentence)]


def split_conversation(
    conversation: str,
    *,
    max_sentences: int = DEFAULT_CHUNK_SENTENCES,
    max_chars: int = DEFAULT_MAX_CHUNK_CHARS,
) -> list[str]:
    """Split a rendered conversation into extraction-sized segments.

    The conversation arrives as ``role: text`` lines. Turn boundaries are kept
    intact where possible so each chunk still reads as a coherent exchange
    rather than a pile of orphaned sentences.
    """
    text = (conversation or "").strip()
    if not text:
        return []

    # Collect (role, body) turns, tolerating input that is one undifferentiated
    # block with no role prefixes at all.
    turns: list[tuple[str | None, str]] = []
    matches = list(_TURN_SPLIT.finditer(text))
    if matches:
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                turns.append((match.group(1).lower(), body))
    else:
        turns = [(None, text)]

    # Expand turns into sentence units, remembering which role each came from.
    units: list[tuple[str | None, str]] = []
    for role, body in turns:
        sentences = [s for s in _SENTENCE_SPLIT.split(body) if s and s.strip()]
        for sentence in sentences or [body]:
            # A single unit can still be oversized — one long run with no
            # sentence punctuation, for example. Hard-split it on word
            # boundaries so the character cap is always honoured; otherwise one
            # giant turn would reintroduce the exact problem chunking exists to
            # prevent.
            units.extend(_hard_split(sentence.strip(), max_chars, role))
        if not sentences:
            units.append((role, body))

    if not units:
        return []

    chunks: list[str] = []
    current: list[tuple[str | None, str]] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        # Re-render the chunk as role-prefixed lines so the fine-tune sees the
        # same shape it was trained on.
        rendered: list[str] = []
        for role, sentence in current:
            rendered.append(f"{role}: {sentence}" if role else sentence)
        chunks.append("\n".join(rendered))
        current = []
        current_chars = 0

    for unit in units:
        unit_chars = len(unit[1]) + (len(unit[0]) + 2 if unit[0] else 0)
        would_exceed_chars = current and (current_chars + unit_chars) > max_chars
        would_exceed_sentences = len(current) >= max_sentences
        if would_exceed_chars or would_exceed_sentences:
            flush()
        current.append(unit)
        current_chars += unit_chars

    flush()

    # A single chunk means chunking would add cost without changing anything.
    if len(chunks) <= 1:
        return [text]
    return chunks


def salvage_json_array(raw: str) -> tuple[list[dict[str, Any]], bool]:
    """Recover complete objects from a possibly truncated JSON array.

    Returns ``(objects, salvaged)``. ``salvaged`` is True when the payload was
    not valid JSON and recovery had to stop early, which tells the caller the
    result is partial.
    """
    if not raw:
        return [], False

    text = raw.strip()

    # Fast path: it parsed cleanly.
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        memories = parsed.get("memories")
        if isinstance(memories, list):
            return [m for m in memories if isinstance(m, dict)], False
    if isinstance(parsed, list):
        return [m for m in parsed if isinstance(m, dict)], False

    # Slow path: walk the array and decode objects one at a time, stopping at
    # the first incomplete element. Everything before that point is intact.
    decoder = json.JSONDecoder()
    start = text.find("[")
    if start == -1:
        return [], False
    index = start + 1
    recovered: list[dict[str, Any]] = []

    while index < len(text):
        while index < len(text) and text[index] in " \t\r\n,":
            index += 1
        if index >= len(text) or text[index] != "{":
            break
        try:
            obj, end = decoder.raw_decode(text, index)
        except ValueError:
            break
        if isinstance(obj, dict):
            recovered.append(obj)
        index = end

    return recovered, True


def claim_key(claim: dict[str, Any]) -> tuple[str, str, str]:
    """Normalised identity for a claim, used to dedupe across chunks."""
    subject = _normalise_whitespace(str(claim.get("subject", ""))).lower()
    predicate = _normalise_whitespace(str(claim.get("predicate", ""))).lower()
    object_value = _normalise_whitespace(str(claim.get("object", ""))).lower()
    return subject, predicate, object_value


def merge_claims(claim_groups: list[list[dict[str, Any]]]) -> ChunkedResult:
    """Flatten, dedupe, and report what happened.

    The first occurrence of a key wins so that chunk order — which follows
    conversation order — is preserved in the result.
    """
    result = ChunkedResult()
    seen: dict[tuple[str, str, str], int] = {}

    for group in claim_groups:
        for claim in group:
            if not isinstance(claim, dict):
                continue
            text = _normalise_whitespace(str(claim.get("text", "")))
            if not text:
                continue
            key = claim_key(claim)
            if all(not part for part in key):
                # No usable triple: fall back to the verbatim text so identical
                # sentences still collapse.
                key = ("", "", text.lower())
            if key in seen:
                result.duplicate_claims += 1
                continue
            seen[key] = len(result.claims)
            result.claims.append(claim)

    return result
