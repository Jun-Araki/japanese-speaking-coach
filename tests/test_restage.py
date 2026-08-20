"""Tests for re-scoring a stored run through a check, without calling the model.

The point of this module is that a stage differs from its source in ONE thing, so
what is pinned here is mostly what must NOT change: the format columns describe the
first answer and no post-processing may touch them, and a run measured on other
items may not be quietly folded into today's table.

The conjunction in check 3 gets its own tests because it is where a plausible
implementation goes wrong — dropping the "small edit" term makes check 3 fire on
the same items as check 1, and two columns that overlap cannot be read as the
effect of one check each.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from correction.engine import Correction
from evals.dataset import Item
from evals.restage import (
    check_one,
    check_three_admission,
    check_three_politeness,
    correction_from_row,
    firing_rates,
    restage,
)
from evals.score import SCORER_VERSION

# Shares almost nothing with the sentence and is far longer: above every distance
# the engine actually produced on 2026-08-19, where the largest was 0.818.
REPLACED = "本日は大変よいお天気でございますね。まったくその通りです。"


def item(
    id: str = "eval-001",
    scene: str = "greeting",
    learner: str = "おはよう",
    needs: bool = True,
) -> Item:
    return Item(
        id=id,
        scene=scene,
        learner_sentence=learner,
        needs_correction=needs,
        corrected_sentence=None,
        reason_en=None,
        split="dev",
    )


def correction(
    corrected: str | None = "おはようございます",
    reason: str | None = "The polite form is expected here.",
    needs: bool = True,
) -> Correction:
    return Correction(needs_correction=needs, corrected_sentence=corrected, reason_en=reason)


def row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "eval-001",
        "scene": "greeting",
        "learner_sentence": "おはよう",
        "expected": True,
        "predicted": True,
        "format_compliant": True,
        "format_problems": [],
        "japanese_left_unquoted": False,
        "japanese_ratio": 0.0,
        "validation_reason": None,
        "discarded_correction": None,
        "elapsed_ms": 1200,
        "attempts": 1,
        "corrected_sentence": "おはようございます",
        "reason_en": "The polite form is expected here.",
    }
    return {**base, **overrides}


def record(rows: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "run_id": "20260819-1741",
        "implementation": "engine",
        "prompt_version": "correction-v1",
        "scorer_version": SCORER_VERSION,
        "items_digest": "758e01ba6d39",
        "split": "dev",
        "level": "beginner",
        "stage": "raw",
        "scorer_checked_on": None,
        "results_redacted": False,
        "results": rows,
    }
    return {**base, **overrides}


class TestCheckOne:
    def test_discards_an_answer_that_replaced_the_sentence(self) -> None:
        result = check_one(item(learner="はい。"), correction(corrected=REPLACED))
        assert result.fired
        assert result.correction.needs_correction is False
        # The thrown-away correction stays readable: a column that scores worse
        # than its source has to be answerable, and a flag cannot answer it.
        assert result.discarded is not None
        assert result.discarded.corrected_sentence == REPLACED

    def test_keeps_an_ordinary_correction(self) -> None:
        assert not check_one(item(), correction()).fired


class TestCheckThreeIsAConjunction:
    def test_does_not_fire_where_check_one_already_would(self) -> None:
        # Both terms would otherwise be satisfied: tier A passes the politeness
        # predicate unconditionally. Only the far rewrite holds it back, and that
        # is the term that keeps the two columns separable.
        result = check_three_politeness(item(learner="はい。"), correction(corrected=REPLACED))
        assert not result.fired

    def test_fires_on_a_small_edit_the_predicate_calls_fine(self) -> None:
        result = check_three_politeness(item(), correction())
        assert result.fired
        assert result.correction.needs_correction is False
        assert result.reason == "no_correction_needed"

    def test_tier_b_scene_is_judged_on_the_ending(self) -> None:
        # workplace_keigo is not tier A, so a plain-form sentence is not waved
        # through — this is the distinction that took the predicate from -7.8pt
        # to +12.2pt on 2026-08-10.
        plain = item(scene="workplace_keigo", learner="資料を送る")
        assert not check_three_politeness(plain, correction(corrected="資料を送ります")).fired

    def test_admission_version_reads_the_models_own_reason(self) -> None:
        conceded = correction(reason="This is grammatically correct, but a bit direct.")
        assert check_three_admission(item(), conceded).fired
        assert not check_three_admission(item(), correction()).fired

    def test_leaves_an_answer_that_proposed_nothing(self) -> None:
        untouched = correction(corrected=None, reason=None, needs=False)
        assert not check_three_politeness(item(), untouched).fired


class TestRestage:
    def test_carries_the_format_columns_through_untouched(self) -> None:
        # The check runs after the answer was written, so it cannot change whether
        # the answer arrived in the right shape. Folding a discard into
        # format_compliance would make the check look like it repaired formatting.
        source = record([row(format_compliant=False, format_problems=["not json"])])
        outcome = restage(source, "check3-politeness").outcomes[0]
        assert outcome.format_compliant is False
        assert outcome.format_problems == ("not json",)
        assert outcome.attempts == 1
        assert outcome.elapsed_ms == 1200

    def test_a_discarded_correction_clears_the_reason_columns(self) -> None:
        # The learner is shown nothing, so a reason that no longer reaches them
        # cannot go on counting against the language figures.
        source = record([row(reason_en="It is 「おはよう」 in casual speech.")])
        outcome = restage(source, "check3-politeness").outcomes[0]
        assert outcome.predicted is False
        assert outcome.reason_en is None
        assert outcome.japanese_left_unquoted is False
        assert outcome.japanese_ratio is None

    def test_an_unusable_verdict_stays_unusable(self) -> None:
        source = record([row(predicted=None, corrected_sentence=None, reason_en=None)])
        outcome = restage(source, "validated").outcomes[0]
        assert outcome.predicted is None
        assert outcome.validation_reason is None

    def test_refuses_a_run_that_is_already_staged(self) -> None:
        with pytest.raises(ValueError, match="raw"):
            restage(record([row()], stage="validated"), "validated")

    def test_refuses_a_redacted_run(self) -> None:
        with pytest.raises(ValueError, match="no per-item rows"):
            restage(record([], results_redacted=True, split="test"), "validated")


class TestFiringRates:
    def test_gap_is_the_already_natural_side_minus_the_needed_side(self) -> None:
        # The pre-registered bar is a gap in points with a sign: a check that fires
        # more often on the corrections the learner needed is failing in the
        # direction that matters, and an absolute difference would hide that.
        rows = [
            row(id="eval-001", expected=False, learner_sentence="おはよう"),
            row(
                id="eval-002",
                expected=True,
                learner_sentence="はい。",
                corrected_sentence=REPLACED,
            ),
        ]
        rates = firing_rates(restage(record(rows), "check3-politeness"))
        assert rates["on_already_natural"] == 1.0
        assert rates["on_needs_correction"] == 0.0
        assert rates["gap_pt"] == 100.0


class TestCorrectionFromRow:
    def test_grounding_is_empty_until_retrieval_lands(self) -> None:
        # Not stored per item, and empty by construction this week. If retrieval
        # ever fills it without the record carrying it, check 3 replayed here would
        # silently measure a different rule than the app runs.
        assert correction_from_row(row()).grounding_ids == ()  # type: ignore[union-attr]

    def test_returns_nothing_where_the_model_never_answered(self) -> None:
        assert correction_from_row(row(predicted=None)) is None


class TestAgainstTheRealRun:
    def test_todays_engine_record_restages_without_loss(self) -> None:
        # Guards the shape of an actual record against this module's assumptions:
        # a missing column here would otherwise only surface as a KeyError on the
        # day the table is built.
        path = Path("evals/runs/20260819-1741-engine-raw-dev.json")
        if not path.exists():  # pragma: no cover - the record is committed with it
            pytest.skip("the 8/19 engine run is not present")
        source = json.loads(path.read_text(encoding="utf-8"))
        report = restage(source, "validated")
        assert len(report.outcomes) == source["n"]
        # Check 1 fired on nothing that day, so this stage has to reproduce the
        # source's numbers exactly. It is the cheapest possible check that the
        # restaging path is not quietly changing verdicts.
        assert report.detection_accuracy == source["detection_accuracy"]
        assert report.over_correction_rate == source["over_correction_rate"]


class TestCheckThreeReadsGrounding:
    """The term the check was supposed to rest on, once retrieval can supply it."""

    def test_does_not_fire_when_an_article_was_cited(self) -> None:
        # "Nothing could be cited" is the main term. A correction the model backed
        # with an article is exactly the one check 3 must not throw away.
        cited = Correction(
            needs_correction=True,
            corrected_sentence="おはようございます",
            reason_en="The polite form is expected here.",
            grounding_ids=("grammar-008",),
        )

        assert not check_three_politeness(item(), cited).fired

    def test_fires_when_nothing_was_cited(self) -> None:
        assert check_three_politeness(item(), correction()).fired

    def test_a_row_without_the_key_counts_as_ungrounded(self) -> None:
        # Runs written before 2026-08-19 carry no grounding_ids and were ungrounded
        # by construction, so an absent key is an honest empty rather than a
        # missing measurement.
        source = record([row()])

        assert restage(source, "check3-politeness").outcomes[0].predicted is False
