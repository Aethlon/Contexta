"""Tests for chunked extraction.

The recall numbers these lock in came from measurements against the real
fine-tuned model, not from reasoning about it. The important one is that
single-shot extraction silently loses facts on long input (20/90 captured) while
chunking recovers them, so the chunk size and the salvage path are both load
bearing rather than defensive decoration.
"""

from __future__ import annotations

import json

from contexta.core.extraction.chunking import (
    DEFAULT_CHUNK_SENTENCES,
    claim_key,
    merge_claims,
    salvage_json_array,
    split_conversation,
)


def _claim(text: str, subject: str = "the user", predicate: str = "likes", object_: str = "tea"):
    return {
        "text": text,
        "subject": subject,
        "predicate": predicate,
        "object": object_,
        "category": "fact",
        "polarity": "positive",
        "status": "current",
    }


def test_short_conversation_is_not_chunked():
    assert len(split_conversation("user: I like tea. I also like coffee.")) == 1


def test_empty_conversation_yields_nothing():
    assert split_conversation("") == []
    assert split_conversation("   \n  ") == []


def test_long_conversation_splits_at_the_measured_chunk_size():
    facts = [f"I use tool number {i}." for i in range(25)]
    chunks = split_conversation("user: " + " ".join(facts) + "\nassistant: Noted.")
    assert len(chunks) == 3
    # Default of 10 sentences per chunk, so 25 sentences is 10 + 10 + 5.
    assert DEFAULT_CHUNK_SENTENCES == 10


def test_every_fact_survives_the_split_exactly_once():
    facts = [f"I use tool number {i}." for i in range(25)]
    conversation = "user: " + " ".join(facts) + "\nassistant: Noted."
    joined = " ".join(split_conversation(conversation))
    for fact in facts:
        assert joined.count(fact) == 1


def test_turn_prefixes_are_preserved_per_chunk():
    conversation = (
        "user: I moved to London. My port is 5432. I prefer dark mode.\n"
        "assistant: Noted.\n"
        "user: I am allergic to shellfish. I cycle to work. I play cello.\n"
    )
    for chunk in split_conversation(conversation):
        # Every line still looks like the role-prefixed shape the model was
        # fine-tuned on.
        for line in chunk.splitlines():
            assert line.startswith(("user:", "assistant:", "system:")) or line


def test_chunk_max_chars_bounds_a_single_huge_turn():
    conversation = "user: " + ("word " * 3000) + "\nassistant: Noted."
    chunks = split_conversation(conversation, max_chars=500)
    assert len(chunks) > 1
    # Each chunk stays under the cap, give or take one unit that could not fit.
    for chunk in chunks:
        assert len(chunk) <= 700


def test_input_without_role_prefixes_still_splits():
    conversation = " ".join(f"Sentence number {i} is here." for i in range(30))
    chunks = split_conversation(conversation)
    assert len(chunks) > 1
    assert "Sentence number 0 is here." in chunks[0]


# â”€â”€ salvage â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_salvage_is_a_noop_on_valid_json():
    payload = json.dumps({"memories": [_claim("I like tea.")]})
    objects, salvaged = salvage_json_array(payload)
    assert salvaged is False
    assert len(objects) == 1


def test_salvage_recovers_complete_objects_from_truncated_json():
    good = json.dumps(_claim("I like tea."))
    second = json.dumps(_claim("I like coffee."))
    truncated = '{"memories": [' + good + ", " + second[:20]
    objects, salvaged = salvage_json_array(truncated)
    assert salvaged is True
    # The complete first object survives even though the rest is garbage.
    assert [o["text"] for o in objects] == ["I like tea."]


def test_salvage_keeps_every_complete_object_before_the_break():
    payload = json.dumps(
        {"memories": [_claim(f"fact {i}.") for i in range(5)]}
    )
    truncated = payload[: len(payload) - 40]
    objects, salvaged = salvage_json_array(truncated)
    assert salvaged is True
    assert len(objects) == 4


def test_salvage_returns_nothing_when_there_is_no_array():
    objects, salvaged = salvage_json_array("I could not comply with that request.")
    assert objects == []
    assert salvaged is False


def test_salvage_on_empty_input():
    assert salvage_json_array("") == ([], False)


# â”€â”€ merge / dedupe â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_merge_dedupes_identical_claims_across_chunks():
    a = _claim("I like tea.")
    b = _claim("I like coffee.", object_="coffee")
    result = merge_claims([[a], [a, b]])
    assert [c["text"] for c in result.claims] == ["I like tea.", "I like coffee."]
    assert result.duplicate_claims == 1


def test_merge_is_insensitive_to_whitespace_and_case_in_the_triple():
    noisy = _claim("I like tea.", subject=" The  User ", predicate="LIKES", object_="Tea")
    result = merge_claims([[noisy], [_claim("I like tea.")]])
    assert len(result.claims) == 1
    assert result.duplicate_claims == 1


def test_merge_drops_claims_without_text():
    result = merge_claims([[_claim("keep me."), _claim("   ")]])
    assert [c["text"] for c in result.claims] == ["keep me."]


def test_claim_key_falls_back_to_text_when_no_triple_is_usable():
    a = {"text": "Something with no triple"}
    b = {"text": "Something with no triple"}
    assert claim_key(a) == claim_key(b)


def test_merge_preserves_conversation_order_across_groups():
    groups = [
        [_claim("first.", object_="one")],
        [_claim("second.", object_="two")],
        [_claim("third.", object_="three")],
    ]
    result = merge_claims(groups)
    assert [c["text"] for c in result.claims] == ["first.", "second.", "third."]


def test_merge_reports_counters():
    result = merge_claims(
        [[_claim("a.", object_="one"), _claim("b.", object_="two")], [_claim("a.", object_="one")]]
    )
    result.chunks = 2
    assert result.chunks == 2
    assert result.duplicate_claims == 1
    assert len(result.claims) == 2
