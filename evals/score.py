"""Scoring: run one implementation over one split and write a run record.

Only `needs_correction` is scored by machine. The corrected sentence is never
compared for equality — natural phrasing is not unique, and exact-match scoring
would report a system far worse than it is (docs/ja/glossary.md §5, and the
llm-jp-eval critique this project is copying its cautions from). How good the
phrasing and the reason actually are is judged by eye, on the scale in §6.

Format compliance is recorded ALONGSIDE the accuracy numbers and never folded into
them. A reason that came back in Japanese is a formatting failure, not a wrong
judgement, and mixing the two produces a number that cannot be acted on.

Nothing here goes through the app. The items are handed to the correction engine as
text, so that the speech stage cannot silently repair a learner's mistake and make
a correct engine look wrong (docs/ja/glossary.md §5).

Run:  .venv/bin/python -m evals.score --implementation baseline --split test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Any, Final

from config import THRESHOLDS_PATH
from correction import PROMPT_VERSION as ENGINE_PROMPT_VERSION
from correction import baseline_check, check
from correction.baseline import PROMPT_VERSION as BASELINE_PROMPT_VERSION
from correction.engine import CorrectionResult, japanese_left_unquoted, japanese_ratio
from correction.validation import validate
from dialogue.scenes import LEVELS
from evals.dataset import ITEMS_PATH, Item, Split, load_items
from llm import active_model_name

RUNS_DIR: Final = Path("evals/runs")

# Bumped whenever a rule in this file changes what counts as a hit — the language
# rule, the denominators, the treatment of an unusable verdict. The prompt version
# alone cannot explain a number that moved because the scorer changed, and a
# scoring bug that nobody can date is the last item in the llm-jp-eval table of
# traps this project copied its cautions from (PLAN.md §2-4).
SCORER_VERSION: Final = "score-v1"

# The dataset carries a scene per item but no level: the level describes a learner,
# and these sentences are not attributed to one. Measurement fixes it at beginner —
# the level the testers in Bangalore are actually at — and records it, because the
# level is part of the prompt and a run measured at another level is not comparable.
MEASUREMENT_LEVEL: Final = "beginner"

# Five items are re-checked by hand after every run, as fixed in design.md. A
# scoring bug and a bad model produce the same disappointing number, and this is
# the only step that tells them apart.
MANUAL_CHECK_SAMPLE: Final = 5

# One learner sentence, one scene, one level, in and a judgement out. Both
# implementations have this shape so that the scoring path is the same for both.
Judge = Callable[[str, str, str], CorrectionResult]

# Stages, not implementations. The validation checks are post-processing over an
# answer that already exists, so the SAME set of answers can be scored with them on
# and off — the difference between two stages is the check and nothing else, with
# no second set of calls and no sampling noise in between (design.md, "段は4つに割る").
STAGES: Final[tuple[str, ...]] = ("raw", "validated")

IMPLEMENTATIONS: Final[dict[str, tuple[Judge, str]]] = {
    "baseline": (baseline_check, BASELINE_PROMPT_VERSION),
    "engine": (check, ENGINE_PROMPT_VERSION),
}


@dataclass(frozen=True)
class Outcome:
    """What one implementation did with one item."""

    item: Item
    # None when the answer never parsed. Kept distinct from False: "said nothing
    # usable" and "said this is fine" are different failures, and collapsing them
    # would hide the first one inside a metric that looks merely mediocre.
    predicted: bool | None
    format_compliant: bool
    # What was wrong with the first answer's form, if anything. Kept per item so a
    # low format_compliance_rate can be read without re-running the measurement.
    format_problems: tuple[str, ...]
    # Recorded, not counted: the correction prompt asks for 「」 and the baseline
    # prompt does not, so this shows where that difference actually lands.
    japanese_left_unquoted: bool
    # Wall-clock for this item's call. Week 4 optimises latency and compares before
    # and after, but "before" is the state of the system on the day week 4 starts —
    # this week's state can only be recorded this week. Kept per item so the
    # aggregate can be recomputed without re-running.
    elapsed_ms: int
    # How far the reason sat from the language threshold, not just which side of it.
    # glossary §7 asks for that threshold to be reconfirmed against dev this week,
    # and a boolean cannot answer "by how much". None when there was no reason.
    japanese_ratio: float | None
    # Which check discarded this correction, if any, and what it discarded. Named
    # rather than counted: when the implementation scores below the baseline the
    # first suspect is the validation throwing away corrections that were fine, and
    # a tally cannot answer that (correction/validation.py).
    validation_reason: str | None
    discarded_correction: str | None
    attempts: int
    corrected_sentence: str | None
    reason_en: str | None

    @property
    def agrees(self) -> bool:
        return self.predicted is self.item.needs_correction


@dataclass(frozen=True)
class ScoreReport:
    """The three week-1 numbers, and the counts they were computed from."""

    outcomes: list[Outcome]

    @property
    def detection_accuracy(self) -> float | None:
        """Of the items labelled `true`, the share the system also called `true`.

        An item with no usable verdict counts against this: the system did not say
        the sentence needed correcting, and the learner would not have been told.
        """
        return _ratio(
            sum(1 for o in self.labelled(True) if o.predicted is True),
            len(self.labelled(True)),
        )

    @property
    def over_correction_rate(self) -> float | None:
        """Of the items labelled `false`, the share the system wrongly called `true`.

        Lower is better. An item with no usable verdict is not counted as an over-
        correction — nothing was proposed — which is the generous reading, so
        `unusable_verdicts` is reported next to it rather than left implicit.
        """
        return _ratio(
            sum(1 for o in self.labelled(False) if o.predicted is True),
            len(self.labelled(False)),
        )

    @property
    def format_compliance_rate(self) -> float | None:
        """Share of items whose FIRST answer was usable JSON with an English reason.

        First answer, even where a retry repaired it: a retry that could erase a
        format failure would be the same lie as dropping the broken items from the
        denominator (docs/ja/glossary.md §5).
        """
        return _ratio(sum(1 for o in self.outcomes if o.format_compliant), len(self.outcomes))

    @property
    def unusable_verdicts(self) -> int:
        return sum(1 for o in self.outcomes if o.predicted is None)

    def labelled(self, needs_correction: bool) -> list[Outcome]:
        """The outcomes for the items carrying one label — the two denominators."""
        return [o for o in self.outcomes if o.item.needs_correction is needs_correction]


def score(
    items: list[Item],
    judge: Judge,
    level: str = MEASUREMENT_LEVEL,
    stage: str = "raw",
) -> ScoreReport:
    """Run one implementation over the items, in the order they were given."""
    return ScoreReport([_judge_item(item, judge, level, stage) for item in items])


def manual_check_sample(outcomes: list[Outcome], size: int = MANUAL_CHECK_SAMPLE) -> list[Outcome]:
    """Pick items to re-check by hand, spread evenly through the run.

    Evenly spaced rather than random: the sample has to be reproducible from the
    run record, and taking the first five would only ever inspect one scene.
    """
    if size >= len(outcomes):
        return list(outcomes)
    step = len(outcomes) / size
    return [outcomes[int(index * step)] for index in range(size)]


def thresholds_digest() -> str:
    """Fingerprint of config/thresholds.toml.

    Changing a threshold moves the numbers and moves neither `prompt_version` nor
    `scorer_version`, so without this the improvement cycle writes two run records
    that are identical in every field and different in what they measured. The
    README is supposed to say what was changed between them; this is what makes
    that recoverable rather than remembered.
    """
    return hashlib.sha256(THRESHOLDS_PATH.read_bytes()).hexdigest()[:12]


def items_digest(path: Path) -> str:
    """Fingerprint of the dataset a run was measured against.

    Without it a run record names the model, the prompt and the scorer but not the
    data, so two runs can carry the same versions and still be measured on
    different item sets. That is not hypothetical here: the day-4 and day-6 runs
    were taken against a 60-item file, and the file now holds 120 — the `test`
    split itself grew from 20 items to 40 between them.

    Twelve hex digits, because this is for telling two datasets apart by eye in a
    README, not for defending against a forged one.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def run_record(
    report: ScoreReport,
    implementation: str,
    prompt_version: str,
    split: Split,
    level: str,
    run_id: str,
    digest: str | None = None,
    scorer_checked_on: str | None = None,
    stage: str = "raw",
) -> dict[str, Any]:
    """The JSON written for every measurement.

    `n` and `split` are mandatory and are the reason this file exists. Without them
    a number in the README cannot be traced back to the measurement it came from —
    and week 1 deliberately measures twice, on 20 items and then on 40, so "which
    run is this?" is a question that will actually be asked (design.md).

    `scorer_checked_on` names the `dev` run whose five items were read by hand
    before this one. On a `test` run that is the whole of the hand check: see
    `_print_manual_check`.
    """
    sample_ids = [outcome.item.id for outcome in manual_check_sample(report.outcomes)]
    redacted = split == "test"
    return {
        "run_id": run_id,
        "implementation": implementation,
        "model": active_model_name(),
        "prompt_version": prompt_version,
        "scorer_version": SCORER_VERSION,
        "thresholds_digest": thresholds_digest(),
        "items_digest": digest,
        "n": len(report.outcomes),
        "split": split,
        "level": level,
        "date": run_id[:8],
        "detection_accuracy": report.detection_accuracy,
        "over_correction_rate": report.over_correction_rate,
        "format_compliance_rate": report.format_compliance_rate,
        "unusable_verdicts": report.unusable_verdicts,
        "stage": stage,
        # Split by label, because the two directions mean opposite things: a check
        # that fires on `false` items is doing its job and one that fires on `true`
        # items is destroying corrections the learner needed. A single total hides
        # exactly the distinction the check is judged on.
        "validation_fired": {
            "on_needs_correction": sum(
                1 for o in report.labelled(True) if o.validation_reason is not None
            ),
            "on_already_natural": sum(
                1 for o in report.labelled(False) if o.validation_reason is not None
            ),
        },
        # An aggregate, so it survives redaction: it says how often a reason named
        # Japanese without quoting it, not whether any particular item was right.
        # It was printed to the console and nowhere else, which left a figure in
        # the steering notes that no record could reproduce.
        "japanese_left_unquoted": sum(1 for o in report.outcomes if o.japanese_left_unquoted),
        "latency_ms": _latency(report.outcomes),
        "manual_check_ids": sample_ids,
        "scorer_checked_on": scorer_checked_on,
        "results_redacted": redacted,
        "results": [] if redacted else [_result_row(outcome) for outcome in report.outcomes],
    }


def _result_row(outcome: Outcome) -> dict[str, Any]:
    """One item's row in a `dev` run record.

    A `test` run writes no rows at all. The first attempt at this kept the format
    columns, on the reasoning that they describe the shape of an answer rather than
    whether it was right — and that was wrong twice over. `japanese_left_unquoted`
    and `reason_not_english` can only be set when the model returned a reason, and a
    reason only exists when it returned a correction, so either one says
    `predicted is True`. Against a dataset that publishes `needs_correction` for
    every item, that recovers the misses exactly: on the day-4 record the four
    `false` items flagged unquoted Japanese ARE the four it got wrong, and
    `over_correction_rate` of 4/7 confirms there are no others.

    A column that only exists when there was an answer is a verdict column. What
    remains for `test` is the aggregate — the score, and no way to see where it came
    from, which is what §7 asks for. Nothing is lost: week 2's error analysis reads
    the `dev` record, which is written in full.
    """
    return {
        "id": outcome.item.id,
        "scene": outcome.item.scene,
        "learner_sentence": outcome.item.learner_sentence,
        "expected": outcome.item.needs_correction,
        "predicted": outcome.predicted,
        "format_compliant": outcome.format_compliant,
        "format_problems": list(outcome.format_problems),
        "japanese_left_unquoted": outcome.japanese_left_unquoted,
        "japanese_ratio": outcome.japanese_ratio,
        "validation_reason": outcome.validation_reason,
        "discarded_correction": outcome.discarded_correction,
        "elapsed_ms": outcome.elapsed_ms,
        "attempts": outcome.attempts,
        "corrected_sentence": outcome.corrected_sentence,
        "reason_en": outcome.reason_en,
    }


def _judge_item(item: Item, judge: Judge, level: str, stage: str = "raw") -> Outcome:
    started = time.perf_counter()
    result = judge(item.learner_sentence, item.scene, level)
    elapsed_ms = round((time.perf_counter() - started) * 1000)

    correction = result.correction
    validation_reason: str | None = None
    discarded: str | None = None
    if stage == "validated" and correction is not None:
        checked = validate(item.learner_sentence, correction)
        correction = checked.correction
        validation_reason = checked.reason
        discarded = None if checked.discarded is None else checked.discarded.corrected_sentence
    reason = None if correction is None else correction.reason_en
    return Outcome(
        item=item,
        predicted=None if correction is None else correction.needs_correction,
        format_compliant=result.format_compliant,
        format_problems=tuple(result.format_problems),
        japanese_left_unquoted=reason is not None and japanese_left_unquoted(reason),
        japanese_ratio=None if reason is None else japanese_ratio(reason),
        validation_reason=validation_reason,
        discarded_correction=discarded,
        elapsed_ms=elapsed_ms,
        attempts=result.attempts,
        corrected_sentence=None if correction is None else correction.corrected_sentence,
        reason_en=None if correction is None else correction.reason_en,
    )


def _latency(outcomes: list[Outcome]) -> dict[str, int | None]:
    """Median and 95th percentile of the per-item call time.

    An aggregate, so it survives redaction on `test`: how long a call took says
    nothing about whether the answer was right. Nearest-rank rather than an
    interpolated percentile — with forty items the interpolation would invent a
    value between two measurements and read as more precise than the run is.
    """
    if not outcomes:
        return {"median": None, "p95": None}
    ordered = sorted(outcome.elapsed_ms for outcome in outcomes)
    return {
        "median": ordered[(len(ordered) - 1) // 2],
        "p95": ordered[min(len(ordered) - 1, ceil(0.95 * len(ordered)) - 1)],
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    # None, not 0.0: an empty group was not measured, and a zero here would be read
    # as a measured zero — which for over_correction_rate is the best possible score.
    if denominator == 0:
        return None
    return numerator / denominator


def _percent(value: float | None) -> str:
    return "not measured" if value is None else f"{value:.1%}"


def _print_summary(report: ScoreReport, implementation: str, split: Split) -> None:
    needs = report.labelled(True)
    natural = report.labelled(False)
    print(f"\n{implementation} on {split}, n={len(report.outcomes)}")
    print(f"  detection_accuracy      {_percent(report.detection_accuracy)}  (n={len(needs)})")
    print(f"  over_correction_rate    {_percent(report.over_correction_rate)}  (n={len(natural)})")
    print(f"  format_compliance_rate  {_percent(report.format_compliance_rate)}")
    print(f"  unusable verdicts       {report.unusable_verdicts}")
    if split != "test":
        # Only ever set on an item the model corrected, so on the held-out split
        # this is a count of `predicted is True` under another name — the exact
        # shape of leak the redaction was written for (see `_result_row`). It stays
        # in the record as an aggregate, where it says how often a reason named
        # Japanese without quoting it and nothing about any single item.
        unquoted = sum(1 for o in report.outcomes if o.japanese_left_unquoted)
        print(f"  japanese left unquoted  {unquoted}  (recorded, not counted)")


def _print_manual_check(report: ScoreReport, split: Split) -> None:
    """Print the five hand-checked items in full — on `dev` only.

    The point of the hand check is to tell a scoring bug apart from a weak model,
    and the only thing that separates them is `expected` against `predicted`. So
    this cannot be softened for `test` by hiding a column or two: printing the
    learner sentence and the system's correction without the verdicts leaves a
    check on the MODEL, which is not what this step is for.

    The redaction in `_result_row` closed the run record and left this open. Five
    of forty is 12.5% of the split, and `over_correction_rate` rests on thirteen
    items — so reading five verdicts means reading the outcome of up to 15% of that
    denominator, days before a week of tuning against `dev`. "Bounded" was the wrong
    defence: week 1's lesson is that a rule kept by discipline is a rule that gets
    broken, and every other leak here was closed by machinery instead.

    Both cannot be had at once. `items.json` publishes `needs_correction` for every
    item, so any per-item line that varies with the answer is `predicted` under
    another name (evals/score.py `_result_row`). The hand check therefore MOVES: a
    handful of `dev` items are scored first, through the same code at the same
    `scorer_version`, and that run's id goes into `scorer_checked_on`. Nothing is
    lost — a scoring bug does not know which split it is on.
    """
    if split == "test":
        ids = ", ".join(outcome.item.id for outcome in manual_check_sample(report.outcomes))
        print("\nNo per-item output on test: a verdict read here is a verdict tuned against.")
        print("  the hand check ran on dev instead, recorded as scorer_checked_on")
        print(f"  ids sampled (labels are public, verdicts are not): {ids}")
        return

    print(f"\nCheck these {MANUAL_CHECK_SAMPLE} by hand before believing the numbers above:")
    for outcome in manual_check_sample(report.outcomes):
        item = outcome.item
        print(f"\n  {item.id}  {item.scene}")
        print(f"    learner   {item.learner_sentence}")
        print(f"    label     {item.needs_correction}    system  {outcome.predicted}")
        if outcome.corrected_sentence:
            print(f"    system's  {outcome.corrected_sentence}")
            print(f"    reason    {outcome.reason_en}")
        if item.needs_correction:
            print(f"    yours     {item.corrected_sentence}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--implementation", choices=sorted(IMPLEMENTATIONS), required=True)
    parser.add_argument(
        "--split",
        choices=["dev", "test"],
        required=True,
        help="test is touched at the start and at the end of August, and nowhere between",
    )
    parser.add_argument(
        "--stage",
        choices=sorted(STAGES),
        default="raw",
        help="raw is the model's answer; validated applies the deterministic checks over it",
    )
    parser.add_argument("--level", choices=sorted(LEVELS), default=MEASUREMENT_LEVEL)
    parser.add_argument("--items", type=Path, default=ITEMS_PATH)
    parser.add_argument(
        "--limit",
        type=int,
        help=(
            "score only the first N items. dev only — it exists so the hand check "
            "before a test run costs a handful of calls instead of the whole split"
        ),
    )
    parser.add_argument(
        "--scorer-checked-on",
        help=(
            "run_id of the dev run whose five items were read by hand first. "
            "Required for --split test, where no per-item output is printed"
        ),
    )
    args = parser.parse_args()

    # A `test` run prints no verdicts, so the hand check has to have happened
    # somewhere else. Asking for the id here is what makes that a step rather than
    # an intention: without it, the cheapest path is to skip the check entirely and
    # publish a number nobody looked behind.
    if args.split == "test" and not args.scorer_checked_on:
        raise SystemExit(
            "test runs need --scorer-checked-on: score a few dev items first, at this "
            "same scorer_version, and pass that run_id. The hand check does not "
            "happen on test (see _print_manual_check)."
        )

    # A partial `test` run would be written to `evals/runs/` looking like every other
    # test record, carrying an `n` that nobody reads as "and the rest was skipped".
    # The one test measurement of the month is not the place to allow a subset.
    if args.limit is not None and args.split == "test":
        raise SystemExit("--limit is for dev. A test run is measured over the whole split.")

    judge, prompt_version = IMPLEMENTATIONS[args.implementation]
    items = [item for item in load_items(args.items) if item.split == args.split]
    if not items:
        raise SystemExit(f"no {args.split} items in {args.items}")
    if args.limit is not None:
        items = items[: args.limit]

    print(f"{args.implementation} over {len(items)} {args.split} items...")
    report = score(items, judge, args.level, args.stage)

    run_id = datetime.now().strftime("%Y%m%d-%H%M")
    record = run_record(
        report,
        args.implementation,
        prompt_version,
        args.split,
        args.level,
        run_id,
        digest=items_digest(args.items),
        scorer_checked_on=args.scorer_checked_on,
        stage=args.stage,
    )
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{run_id}-{args.implementation}-{args.stage}-{args.split}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    _print_summary(report, args.implementation, args.split)
    _print_manual_check(report, args.split)
    print(f"\nrun record -> {path}")


if __name__ == "__main__":
    main()
