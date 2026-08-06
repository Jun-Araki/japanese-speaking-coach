"""Tests for the scoring script.

These matter more than they look. A bug in the scorer and a weak model produce the
same disappointing number, and the number is the deliverable of week 1 — so every
rule that decides how a judgement is counted is pinned here, against a fake judge
that never calls a provider:

  - which denominator each metric uses,
  - what happens to an item the implementation could not answer at all,
  - that format compliance stays out of the accuracy numbers,
  - that the run record carries `n` and `split`, without which a number in the
    README cannot be traced to the run it came from.
"""

from __future__ import annotations

from typing import Any

from correction.engine import Correction, CorrectionResult
from evals.dataset import Item
from evals.score import (
    SCORER_VERSION,
    ScoreReport,
    manual_check_sample,
    run_record,
    score,
)


def make_item(
    item_id: str,
    needs_correction: bool,
    scene: str = "greeting",
    split: str = "test",
) -> Item:
    return Item(
        id=item_id,
        scene=scene,
        learner_sentence="おはようです",
        needs_correction=needs_correction,
        corrected_sentence="おはようございます" if needs_correction else None,
        reason_en="A fixed phrase." if needs_correction else None,
        split=split,  # type: ignore[arg-type]
    )


class FakeJudge:
    """Answers with the verdicts it was given, one per call.

    A verdict of None stands for an answer that never parsed, which is the case
    the metrics have to treat differently from "this sentence is fine".
    """

    def __init__(self, *verdicts: bool | None, compliant: bool = True) -> None:
        self.verdicts = list(verdicts)
        self.compliant = compliant
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, sentence: str, scene: str, level: str) -> CorrectionResult:
        self.calls.append((sentence, scene, level))
        verdict = self.verdicts.pop(0)
        problems: tuple[Any, ...] = () if self.compliant else ("invalid_json",)
        if verdict is None:
            return CorrectionResult(sentence, None, 1, problems or ("invalid_json",))
        correction = Correction(
            needs_correction=verdict,
            corrected_sentence="おはようございます" if verdict else None,
            reason_en="A fixed phrase." if verdict else None,
        )
        return CorrectionResult(sentence, correction, 1, problems)


class TestDetectionAccuracy:
    def test_counts_only_the_items_labelled_true(self) -> None:
        items = [make_item("a", True), make_item("b", True), make_item("c", False)]
        # The `false` item is answered `true` — an over-correction, which must not
        # move detection accuracy in either direction.
        report = score(items, FakeJudge(True, False, True))

        assert report.detection_accuracy == 0.5
        assert report.over_correction_rate == 1.0

    def test_an_unusable_verdict_counts_as_not_detected(self) -> None:
        # The learner would not have been told anything, so the system did not
        # detect it. Silently dropping it would inflate the number instead.
        report = score([make_item("a", True), make_item("b", True)], FakeJudge(True, None))

        assert report.detection_accuracy == 0.5
        assert report.unusable_verdicts == 1

    def test_is_none_when_no_item_carries_the_label(self) -> None:
        # Not 0.0 — nothing was measured, and a zero here reads as a measured zero.
        report = score([make_item("a", False)], FakeJudge(False))

        assert report.detection_accuracy is None
        assert report.over_correction_rate == 0.0


class TestOverCorrectionRate:
    def test_counts_only_the_items_labelled_false(self) -> None:
        items = [make_item("a", False), make_item("b", False), make_item("c", True)]
        report = score(items, FakeJudge(True, False, False))

        assert report.over_correction_rate == 0.5

    def test_an_unusable_verdict_is_not_an_over_correction(self) -> None:
        # Nothing was proposed, so nothing was over-corrected. This is the generous
        # reading, which is why unusable_verdicts is reported next to the rate.
        report = score([make_item("a", False), make_item("b", False)], FakeJudge(None, False))

        assert report.over_correction_rate == 0.0
        assert report.unusable_verdicts == 1


class TestFormatCompliance:
    def test_is_measured_over_every_item(self) -> None:
        items = [make_item("a", True), make_item("b", False)]
        report = score(items, FakeJudge(True, False, compliant=False))

        assert report.format_compliance_rate == 0.0

    def test_does_not_touch_the_accuracy_numbers(self) -> None:
        # A reason that came back in Japanese is a formatting failure, not a wrong
        # judgement (docs/ja/glossary.md §5).
        items = [make_item("a", True), make_item("b", False)]
        report = score(items, FakeJudge(True, False, compliant=False))

        assert report.detection_accuracy == 1.0
        assert report.over_correction_rate == 0.0


class TestScoringInputs:
    def test_every_item_is_judged_with_its_own_scene_and_one_level(self) -> None:
        items = [make_item("a", True, scene="greeting"), make_item("b", True, scene="thanks")]
        judge = FakeJudge(True, True)
        score(items, judge, level="upper_beginner")

        assert [call[1] for call in judge.calls] == ["greeting", "thanks"]
        assert {call[2] for call in judge.calls} == {"upper_beginner"}


class TestManualCheckSample:
    def test_is_spread_through_the_run_and_not_the_first_five(self) -> None:
        # Taking the first five would only ever inspect the first scene.
        outcomes = score([make_item(str(n), True) for n in range(20)], FakeJudge(*[True] * 20))
        sample = manual_check_sample(outcomes.outcomes)

        assert [outcome.item.id for outcome in sample] == ["0", "4", "8", "12", "16"]

    def test_returns_everything_when_the_run_is_smaller_than_the_sample(self) -> None:
        outcomes = score([make_item("a", True)], FakeJudge(True))

        assert len(manual_check_sample(outcomes.outcomes)) == 1

    def test_is_reproducible_from_the_run_record(self) -> None:
        report = score([make_item(str(n), True) for n in range(20)], FakeJudge(*[True] * 20))
        record = run_record(report, "baseline", "baseline-v1", "test", "beginner", "20260806-0730")

        assert record["manual_check_ids"] == ["0", "4", "8", "12", "16"]


class TestRunRecord:
    def _record(self, report: ScoreReport) -> dict[str, Any]:
        return run_record(report, "baseline", "baseline-v1", "test", "beginner", "20260806-0730")

    def test_carries_n_and_split(self) -> None:
        # Week 1 measures the baseline twice, on 20 items and then on 40. Without
        # these two fields the README's number cannot be traced to either run.
        report = score([make_item("a", True), make_item("b", False)], FakeJudge(True, False))
        record = self._record(report)

        assert record["n"] == 2
        assert record["split"] == "test"
        assert record["date"] == "20260806"

    def test_carries_the_prompt_version_and_the_model(self, monkeypatch: Any) -> None:
        # Both move the numbers on their own, so a run without them cannot be
        # compared with the next one (docs/ja/glossary.md §7).
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
        record = self._record(score([make_item("a", True)], FakeJudge(True)))

        assert record["prompt_version"] == "baseline-v1"
        assert record["model"] == "gemini/gemini-2.5-flash"
        # The scorer moves the numbers too: a rule change here is invisible in the
        # prompt version, and a number that moved for that reason would be read as
        # a change in the model.
        assert record["scorer_version"] == SCORER_VERSION

    def test_keeps_every_item_level_result(self) -> None:
        # Week 2's error analysis reads these rows; re-running to get them back
        # would cost another set of calls and would not be the same run.
        report = score([make_item("a", True), make_item("b", False)], FakeJudge(False, False))
        results = self._record(report)["results"]

        assert [row["id"] for row in results] == ["a", "b"]
        assert results[0]["expected"] is True
        assert results[0]["predicted"] is False

    def test_an_unusable_verdict_is_visible_in_the_record(self) -> None:
        report = score([make_item("a", True)], FakeJudge(None))
        record = self._record(report)

        assert record["unusable_verdicts"] == 1
        assert record["results"][0]["predicted"] is None
