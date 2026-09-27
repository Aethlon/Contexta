from benchmarks.locomo.run_benchmark import _answer_consistency_guard, _answer_consistency_override


def test_temporal_guard_rejects_conflicting_year() -> None:
    assert _answer_consistency_guard(2, "2019", "21 January 2022", "When did she watch it?") is not None


def test_temporal_guard_accepts_week_before_interval() -> None:
    assert _answer_consistency_guard(2, "The week before 1 January 2023", "2022-12-27", "When did he join?") is None


def test_temporal_guard_rejects_wrong_week() -> None:
    assert _answer_consistency_guard(2, "The week before 1 January 2023", "03 August 2023", "When did he join?") is not None


def test_temporal_override_accepts_equivalent_iso_date() -> None:
    assert _answer_consistency_override(2, "7 May 2023", "2023-05-07", "When did she go?") is True


def test_list_guard_requires_all_items() -> None:
    reason = _answer_consistency_guard(
        1,
        "Kickboxing, Taekwondo",
        "John has done kickboxing and circuit training.",
        "What martial arts has John done?",
    )

    assert reason is not None
    assert "taekwondo" in reason


def test_yes_no_guard_rejects_contradiction() -> None:
    assert _answer_consistency_guard(1, "No", "Yes.", "Do both have pets?") is not None
