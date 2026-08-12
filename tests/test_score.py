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

import json
from pathlib import Path
from typing import Any

import pytest

from config import THRESHOLDS_PATH
from correction.engine import Correction, CorrectionResult
from correction.engine import format_problems as engine_format_problems
from evals.dataset import Item
from evals.score import (
    MEASUREMENT_LEVEL,
    SCORER_VERSION,
    ScoreReport,
    _print_manual_check,
    items_digest,
    main,
    manual_check_sample,
    run_record,
    score,
    thresholds_digest,
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

    def __init__(
        self, *verdicts: bool | None, compliant: bool = True, japanese_reason: bool = False
    ) -> None:
        self.verdicts = list(verdicts)
        self.compliant = compliant
        # Every derived per-item column has to be able to differ between two runs, or
        # a test that compares two runs row by row cannot see that column at all. The
        # reason is English by default; `japanese_left_unquoted` is then False on
        # every item of every run, and a redaction that leaks it looks identical to
        # one that does not (evals/score.py: that leak is how the day-4 misses were
        # recovered the first time).
        #
        # `_result_row` names two columns of that kind, so a Japanese reason has to
        # drag the second one with it. In the real engine a reason is only checked for
        # English when there is a reason at all, which only happens on an item the
        # model corrected — so `reason_not_english` is verdict-dependent in exactly
        # the same way. A fake that reports Japanese as format-compliant is a state
        # the engine cannot produce, and it leaves that column untested.
        self.japanese_reason = japanese_reason
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, sentence: str, scene: str, level: str) -> CorrectionResult:
        self.calls.append((sentence, scene, level))
        verdict = self.verdicts.pop(0)
        problems: tuple[Any, ...] = () if self.compliant else ("invalid_json",)
        if verdict is None:
            return CorrectionResult(sentence, None, 1, problems or ("invalid_json",))
        reason = "これは丁寧ではありません。" if self.japanese_reason else "A fixed phrase."
        if verdict and self.japanese_reason:
            problems = (*problems, "reason_not_english")
        correction = Correction(
            needs_correction=verdict,
            corrected_sentence="おはようございます" if verdict else None,
            reason_en=reason if verdict else None,
        )
        return CorrectionResult(sentence, correction, 1, problems)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "scorer_regression.json"
FIXTURE_CASES: list[dict[str, Any]] = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]
FIXTURE_ITEMS = [
    Item(
        id=case["id"],
        scene=case["scene"],
        learner_sentence=case["learner_sentence"],
        needs_correction=case["needs_correction"],
        corrected_sentence=case["corrected_sentence"],
        reason_en="Reference reason." if case["needs_correction"] else None,
        split="dev",
    )
    for case in FIXTURE_CASES
]


class FixtureJudge:
    """Replays the frozen answers, through the engine's own format check.

    Unlike `FakeJudge` this does not hand `format_problems` over ready-made: it
    builds the `Correction` and asks `correction.engine.format_problems` about it,
    which is where the language rule actually lives.
    """

    def __init__(self) -> None:
        self.remaining = list(FIXTURE_CASES)

    def __call__(self, sentence: str, scene: str, level: str) -> CorrectionResult:
        case = self.remaining.pop(0)
        if case["predicted"] is None:
            return CorrectionResult(sentence, None, 2, ("invalid_json",))
        correction = Correction(
            needs_correction=case["predicted"],
            corrected_sentence=case["corrected_sentence"] if case["predicted"] else None,
            reason_en=case["reason"],
        )
        return CorrectionResult(sentence, correction, 1, engine_format_problems(correction))


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
    def _record(self, report: ScoreReport, split: str = "test") -> dict[str, Any]:
        return run_record(
            report,
            "baseline",
            "baseline-v1",
            split,  # type: ignore[arg-type]
            "beginner",
            "20260806-0730",
        )

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

    def test_keeps_every_item_level_result_on_dev(self) -> None:
        # Week 2's error analysis reads these rows; re-running to get them back
        # would cost another set of calls and would not be the same run.
        report = score([make_item("a", True), make_item("b", False)], FakeJudge(False, False))
        results = self._record(report, "dev")["results"]

        assert [row["id"] for row in results] == ["a", "b"]
        assert results[0]["expected"] is True
        assert results[0]["predicted"] is False

    def test_an_unusable_verdict_is_visible_in_the_record(self) -> None:
        report = score([make_item("a", True)], FakeJudge(None))
        record = self._record(report, "dev")

        assert record["unusable_verdicts"] == 1
        assert record["results"][0]["predicted"] is None

    def test_a_test_run_leaves_nothing_per_item_to_recover_a_verdict_from(self) -> None:
        """Two runs that disagree on every item must write the same rows.

        Asserting that certain field NAMES are absent is a test of spelling, and the
        first attempt at this redaction passed such a test while still giving up all
        four of the day-4 misses: it kept `japanese_left_unquoted`, which is only ever
        set when the model returned a reason, which only happens when it returned a
        correction. Against published labels that is `predicted` under another name.

        So the property, not the spelling: whatever a `test` record says per item, it
        has to say the same thing when every verdict is inverted.

        The reasons are Japanese here on purpose. `japanese_left_unquoted` can only
        be set on an item the model corrected, so with an English reason it is False
        on every row of both runs and the two records match in that column whether or
        not it is redacted — the test would pass while the leak it was written for is
        wide open.
        """
        items = [make_item("a", True), make_item("b", False)]
        all_right = self._record(score(items, FakeJudge(True, False, japanese_reason=True)))
        all_wrong = self._record(score(items, FakeJudge(False, True, japanese_reason=True)))

        assert all_right["results_redacted"] is True
        assert all_right["results"] == all_wrong["results"]
        # And the run is still worth having: the scores themselves differ.
        assert all_right["detection_accuracy"] != all_wrong["detection_accuracy"]

    def test_carries_the_digest_of_the_dataset_it_was_measured_against(self) -> None:
        # Model, prompt and scorer were already recorded; the data was not. Two runs
        # can agree on all three and still have been scored against different item
        # sets — which is exactly what happened to the day-4 and day-6 runs, taken
        # against a 60-item file that has since become 120.
        report = score([make_item("a", True)], FakeJudge(True))
        record = run_record(
            report, "baseline", "baseline-v1", "test", "beginner", "20260806-0730", digest="abc123"
        )

        assert record["items_digest"] == "abc123"

    def test_names_the_dev_run_the_hand_check_was_done_on(self) -> None:
        # A test run prints no verdicts, so the hand check happens elsewhere. The id
        # is what makes that a step instead of an intention.
        report = score([make_item("a", True)], FakeJudge(True))
        record = run_record(
            report,
            "baseline",
            "baseline-v1",
            "test",
            "beginner",
            "20260806-0730",
            scorer_checked_on="20260806-0715",
        )

        assert record["scorer_checked_on"] == "20260806-0715"

    def test_a_test_run_still_records_the_numbers(self) -> None:
        """Redaction costs the per-item rows, not the measurement.

        Week 2's error analysis reads the `dev` record, which is written in full; what
        a `test` run is for is the number.
        """
        report = score([make_item("a", True), make_item("b", False)], FakeJudge(False, True))
        record = self._record(report)

        assert record["detection_accuracy"] == 0.0
        assert record["over_correction_rate"] == 1.0
        assert record["format_compliance_rate"] == 1.0
        assert record["unusable_verdicts"] == 0
        assert record["n"] == 2


class TestConsoleOutput:
    """The run record was redacted for `test`; the console was not.

    Same property as the record test, for the same reason: whatever a `test` run
    prints per item, it has to print the same thing when every verdict is inverted.
    Naming the fields it must not print would be a spelling test again.
    """

    def test_a_test_run_prints_nothing_that_varies_with_the_verdicts(self, capsys: Any) -> None:
        items = [make_item("a", True), make_item("b", False)]

        _print_manual_check(score(items, FakeJudge(True, False, japanese_reason=True)), "test")
        all_right = capsys.readouterr().out
        _print_manual_check(score(items, FakeJudge(False, True, japanese_reason=True)), "test")
        all_wrong = capsys.readouterr().out

        assert all_right == all_wrong

    def test_a_dev_run_still_prints_the_verdicts(self, capsys: Any) -> None:
        # Moving the hand check to dev is only honest if dev still shows enough to
        # do it with: expected against predicted is the whole of the check.
        report = score([make_item("a", True)], FakeJudge(False))
        _print_manual_check(report, "dev")
        printed = capsys.readouterr().out

        assert "label     True" in printed
        assert "system  False" in printed


class TestTestSplitGuard:
    """The guard lives in `main`, so `main` is what gets tested.

    Week 1 wrote `refuse_if_graded()` and tested the function while the accident
    ran through `--run`. The same shape of mistake would be to test a helper here
    and leave the command line able to produce a `test` record with no hand check
    behind it.
    """

    def test_a_test_run_without_a_dev_hand_check_refuses_before_calling_anything(
        self, monkeypatch: Any
    ) -> None:
        # The items path is deliberately missing. The guard has to fire before the
        # dataset is even opened, so with it in place this raises SystemExit about
        # the flag; with it removed the missing file stops the run instead, and the
        # assertion below goes red.
        #
        # The first version of this test passed a real items path, and removing the
        # guard did not turn it red — it sent the suite down `main` into forty live
        # provider calls until pytest timed out. A test whose failure mode is a
        # billable hang is worse than no test: nobody runs the suite to find out.
        monkeypatch.setattr(
            "sys.argv",
            ["score", "--implementation", "baseline", "--split", "test", "--items", "nope.json"],
        )
        with pytest.raises(SystemExit) as excinfo:
            main()

        assert "--scorer-checked-on" in str(excinfo.value)

    def test_a_test_run_cannot_be_limited_to_a_subset(self, monkeypatch: Any) -> None:
        # A partial test record looks like a whole one in `evals/runs/`, and its `n`
        # does not say "the rest was skipped". The month has one test measurement.
        monkeypatch.setattr(
            "sys.argv",
            [
                "score", "--implementation", "baseline", "--split", "test",
                "--scorer-checked-on", "20260811-0700", "--limit", "5",
                "--items", "nope.json",
            ],
        )
        with pytest.raises(SystemExit) as excinfo:
            main()

        assert "--limit is for dev" in str(excinfo.value)

    def test_a_dev_run_does_not_need_one(self, monkeypatch: Any) -> None:
        # dev prints the verdicts itself, so there is nothing to point elsewhere.
        monkeypatch.setattr(
            "sys.argv",
            ["score", "--implementation", "baseline", "--split", "dev", "--items", "nope.json"],
        )
        with pytest.raises((SystemExit, FileNotFoundError)) as excinfo:
            main()

        assert "--scorer-checked-on" not in str(excinfo.value)


class TestExistingMetricsDoNotMove:
    """A frozen expectation for the three week-1 numbers, through the real path.

    Week 2 adds metrics and record fields under a rule: the existing three keep the
    same definition, so `scorer_version` stays put and the 8/11 baseline stays
    comparable with everything measured after it. The rule is written in four
    places, and "we did not change it" is not something a README reader can check.

    Three things this deliberately does, after an audit found the first version
    short of all of them:

    - The cases live in `tests/fixtures/scorer_regression.json`, not in this file.
      A number that moves has to show up as a diff against data, and a fixture that
      can be edited in the same breath as the code it pins is not a fixture.
    - The values are read off `run_record()`, not off `ScoreReport`. Week 2 adds
      six fields to that record; the point is that adding them moves nothing.
    - The reasons go through `correction.engine.format_problems`, so the language
      rule is exercised. `SCORER_VERSION` says it covers "the language rule", but
      that rule lives in the engine, and it was edited on 8/11 AFTER the official
      test measurement without the version moving. The earlier fake returned
      `format_problems` ready-made and never touched it — the one path that most
      needed pinning was the one path the test could not see.
    """

    def _report(self) -> ScoreReport:
        return score(FIXTURE_ITEMS, FixtureJudge(), MEASUREMENT_LEVEL)

    def test_the_three_numbers_are_unchanged(self) -> None:
        record = run_record(
            self._report(), "baseline", "baseline-v1", "dev", MEASUREMENT_LEVEL, "20260811-0000"
        )

        assert record["detection_accuracy"] == 0.5  # 2 of 4 labelled true
        assert record["over_correction_rate"] == pytest.approx(2 / 3)  # 2 of 3 labelled false
        # 5 of 7, and the two failures are different failures. fix-007 came back
        # in Japanese; fix-004 never parsed, and unparseable output is a format
        # failure as well as a missed detection — the same item is counted in both
        # places on purpose, because they are answers to different questions.
        #
        # This expectation was written as 6/7 twice, by hand, on the reasoning that
        # an unusable verdict "has no reason to judge". Both times the fixture said
        # otherwise. That is the argument for having one.
        #
        # fix-002 names ございます without quotes and still passes: an English
        # sentence mentioning a Japanese word is English (docs/ja/glossary.md §5).
        assert record["format_compliance_rate"] == pytest.approx(5 / 7)
        assert record["unusable_verdicts"] == 1

    def test_the_language_rule_still_splits_the_same_reasons(self) -> None:
        # fix-002 names ございます without quotes and is English; fix-007 is written
        # in Japanese. Both are recorded as unquoted Japanese; only one is a
        # failure. Reversing that was the day-4 bug, and this is what would catch
        # it returning.
        report = self._report()
        by_id = {outcome.item.id: outcome for outcome in report.outcomes}

        assert by_id["fix-002"].format_compliant is True
        assert by_id["fix-007"].format_compliant is False
        assert by_id["fix-002"].japanese_left_unquoted is True
        assert by_id["fix-007"].japanese_left_unquoted is True

    def test_the_denominators_are_unchanged(self) -> None:
        # The two accuracy numbers do not share a denominator, and week 1 corrected
        # the error margin twice for getting that wrong.
        report = self._report()

        assert len(report.labelled(True)) == 4
        assert len(report.labelled(False)) == 3


class TestProvenanceFields:
    """What a record has to carry for two runs to be comparable at all.

    Model, prompt and scorer were recorded from week 1. The data and the thresholds
    were not, and both move the numbers: the improvement cycle changes one thing and
    writes two records, and if that thing was a threshold then every field in the
    two records is identical.
    """

    def _record(self, split: str = "dev") -> dict[str, Any]:
        report = score([make_item("a", True), make_item("b", False)], FakeJudge(True, False))
        return run_record(
            report,
            "baseline",
            "baseline-v1",
            split,  # type: ignore[arg-type]
            MEASUREMENT_LEVEL,
            "20260811-0000",
        )

    def test_the_thresholds_are_fingerprinted(self) -> None:
        record = self._record()

        assert record["thresholds_digest"] == thresholds_digest()
        assert len(record["thresholds_digest"]) == 12

    def test_the_fingerprint_follows_the_file(self, tmp_path: Path, monkeypatch: Any) -> None:
        # A digest that does not move when the file moves is worse than none: it
        # says the thresholds were the same when nobody checked.
        before = thresholds_digest()
        edited = tmp_path / "thresholds.toml"
        edited.write_text(THRESHOLDS_PATH.read_text(encoding="utf-8") + "\n# touched\n")
        monkeypatch.setattr("evals.score.THRESHOLDS_PATH", edited)

        assert thresholds_digest() != before

    def test_latency_is_an_aggregate_and_survives_redaction(self) -> None:
        # How long a call took says nothing about whether the answer was right, so
        # it belongs in a `test` record where the per-item rows do not.
        record = self._record("test")

        assert record["results"] == []
        assert set(record["latency_ms"]) == {"median", "p95"}
        assert record["latency_ms"]["median"] is not None


class TestItemsDigest:
    def test_changes_when_the_dataset_changes(self, tmp_path: Path) -> None:
        first = tmp_path / "a.json"
        second = tmp_path / "b.json"
        first.write_text('[{"id": "eval-001"}]', encoding="utf-8")
        second.write_text('[{"id": "eval-002"}]', encoding="utf-8")

        assert items_digest(first) != items_digest(second)
        assert len(items_digest(first)) == 12
