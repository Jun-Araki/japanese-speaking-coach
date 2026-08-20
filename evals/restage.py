"""Re-score a stored run through a validation stage, with no second call.

The whole claim behind the comparison table is that a stage differs from the one
before it by ONE thing. Scoring `--stage validated` from `evals.score` would call
the model again, and two runs of a probabilistic model differ by sampling noise as
well as by the check — so the column labelled "the effect of check 1" would carry
an unknown amount of "and it was asked a second time" inside it.

The checks are pure post-processing (correction/validation.py), so the answers
already written to a run record are all that is needed. This module reads a `raw`
run record and applies a check over its rows, producing a run record that differs
from its source in exactly the check and nothing else.

GROUNDING IS READ FROM THE RECORD, NOT ASSUMED. Stage 0 was measured on a prompt
that fixes `grounding_ids` to an empty array, so check 3's main term — "nothing
could be cited" — is true for every one of its items, and what a check 3 column
restaged from it measures is the remaining predicate on its own. That is stated in
requirements §7 of the week-3 steering directory and has to be repeated wherever
the column appears: restaged from an ungrounded run, check 3 cannot decide whether
check 3 is adopted. Restaged from the grounded run (`correction-rag-v1`, measured
2026-08-19) the term means what it was meant to mean, and `score_min = 0` makes it
false for every item that cited anything.

Run:  .venv/bin/python -m evals.restage --run evals/runs/<id>-engine-raw-dev.json \
          --stage validated
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from correction.engine import Correction, japanese_left_unquoted, japanese_ratio
from correction.validation import (
    Validation,
    admits_the_sentence_was_fine,
    politeness_looks_sufficient,
    rewritten_too_far,
    validate,
)
from evals.dataset import ITEMS_PATH, Item, Split
from evals.score import RUNS_DIR, SCORER_VERSION, Outcome, ScoreReport, items_digest, run_record


def check_one(item: Item, correction: Correction) -> Validation:
    """Stage 2: the rewrite-too-far check, exactly as the app would apply it."""
    return validate(item.learner_sentence, correction)


def _check_three(item: Item, correction: Correction, admits: bool) -> Validation:
    """The shared body of check 3: a conjunction, with one term swapped in.

    The rule is "nothing could be cited, the edit is small, and the sentence was
    already fine" (PLAN.md §2-1).

    THE FIRST TERM ONLY STARTED MEANING SOMETHING ON 2026-08-20. Restaged from an
    ungrounded run it is true for every item, so the check reduces to the remaining
    predicate and cannot be judged — which is what requirements §7 said in advance
    and what the first measurement of it showed. Restaged from a grounded run it
    separates the items the model could cite an article for from the ones it could
    not, which is the term the whole check was supposed to rest on.

    The second term is the complement of check 1: a far rewrite is check 1's
    business, and letting check 3 also fire there would make the two columns overlap
    on the same items and stop being separable.
    """
    if not correction.needs_correction or correction.corrected_sentence is None:
        return Validation(correction=correction)
    if correction.grounding_ids:
        return Validation(correction=correction)
    if rewritten_too_far(item.learner_sentence, correction.corrected_sentence):
        return Validation(correction=correction)
    if not admits:
        return Validation(correction=correction)
    return Validation(
        correction=Correction(
            needs_correction=False,
            corrected_sentence=None,
            reason_en=None,
            grounding_ids=correction.grounding_ids,
        ),
        discarded=correction,
        reason="no_correction_needed",
    )


def check_three_politeness(item: Item, correction: Correction) -> Validation:
    """Stage 3a: "already fine" read off the scene's politeness tier.

    Tier A passes unconditionally; tiers B and C are judged on the ending. Measured
    on 2026-08-10 at +12.2pt, against a pre-registered bar of 20pt.
    """
    return _check_three(
        item,
        correction,
        politeness_looks_sufficient(item.learner_sentence, item.scene),
    )


def check_three_admission(item: Item, correction: Correction) -> Validation:
    """Stage 3b: "already fine" read off the model conceding it in its own reason.

    The four phrases were frozen in `ADMISSION_PHRASES` before this run, which is
    the whole of what makes the 20pt bar a bar. Measured at +35.2pt on the
    BASELINE's reasons; this run is the first time it is counted on the real
    implementation's, which is what week 2's design asked for.
    """
    reason = correction.reason_en or ""
    return _check_three(item, correction, admits_the_sentence_was_fine(reason))


# Named stages rather than a flag, because the table has a column per stage and a
# run record has to say which one it is without anybody remembering the flags.
Restage = Callable[[Item, Correction], Validation]

RESTAGES: Final[dict[str, Restage]] = {
    "validated": check_one,
    "check3-politeness": check_three_politeness,
    "check3-admission": check_three_admission,
}


def item_from_row(row: dict[str, Any], split: Split) -> Item:
    """Rebuild the item as it was measured, from the run record itself.

    From the record rather than from `data/evaluation/items.json`, so that a run
    re-staged after the dataset moved cannot silently score old answers against new
    labels. The caller checks the digests; this keeps the two sources from being
    mixed even if that check is ever removed.
    """
    return Item(
        id=row["id"],
        scene=row["scene"],
        learner_sentence=row["learner_sentence"],
        needs_correction=row["expected"],
        corrected_sentence=None,
        reason_en=None,
        split=split,
    )


def correction_from_row(row: dict[str, Any]) -> Correction | None:
    """The answer the model gave, or None where it never produced a usable one."""
    if row["predicted"] is None:
        return None
    return Correction(
        needs_correction=row["predicted"],
        corrected_sentence=row["corrected_sentence"],
        reason_en=row["reason_en"],
        # Read from the record where it is present. Runs written before 2026-08-19
        # did not carry it and were all ungrounded by construction, so an absent
        # key is an honest empty rather than a missing measurement.
        grounding_ids=tuple(row.get("grounding_ids", ())),
    )


def restage(record: dict[str, Any], stage: str) -> ScoreReport:
    """Apply one check over a stored run's answers."""
    if record["stage"] != "raw":
        raise ValueError(f"can only restage a raw run, not {record['stage']!r}")
    if record["results_redacted"] or not record["results"]:
        raise ValueError("this run record carries no per-item rows to restage")

    apply = RESTAGES[stage]
    outcomes: list[Outcome] = []
    for row in record["results"]:
        item = item_from_row(row, record["split"])
        correction = correction_from_row(row)
        validation = None if correction is None else apply(item, correction)
        checked = None if validation is None else validation.correction
        reason = None if checked is None else checked.reason_en
        outcomes.append(
            Outcome(
                item=item,
                predicted=None if checked is None else checked.needs_correction,
                # Carried over untouched: these describe the FIRST answer the model
                # gave, and no post-processing can change what it wrote.
                format_compliant=row["format_compliant"],
                format_problems=tuple(row["format_problems"]),
                japanese_left_unquoted=reason is not None and japanese_left_unquoted(reason),
                japanese_ratio=None if reason is None else japanese_ratio(reason),
                validation_reason=None if validation is None else validation.reason,
                discarded_correction=(
                    None
                    if validation is None or validation.discarded is None
                    else validation.discarded.corrected_sentence
                ),
                elapsed_ms=row["elapsed_ms"],
                attempts=row["attempts"],
                corrected_sentence=None if checked is None else checked.corrected_sentence,
                reason_en=reason,
                grounding_ids=() if checked is None else tuple(checked.grounding_ids),
            )
        )
    return ScoreReport(outcomes)


def firing_rates(report: ScoreReport) -> dict[str, float | None]:
    """How often the check fired on each label, and the gap between them.

    The pre-registered bar for check 3 is stated as a gap in percentage points
    between the two labels, so the gap is computed here rather than left for
    whoever reads the record to subtract — a bar that has to be recomputed by hand
    every time is a bar that will eventually be recomputed differently.
    """
    rates: dict[str, float | None] = {}
    for label, key in ((False, "on_already_natural"), (True, "on_needs_correction")):
        group = report.labelled(label)
        rates[key] = (
            None
            if not group
            else sum(1 for o in group if o.validation_reason is not None) / len(group)
        )
    natural, needed = rates["on_already_natural"], rates["on_needs_correction"]
    rates["gap_pt"] = None if natural is None or needed is None else (natural - needed) * 100
    return rates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="a raw run record to restage")
    parser.add_argument("--stage", choices=sorted(RESTAGES), required=True)
    parser.add_argument("--items", type=Path, default=ITEMS_PATH)
    args = parser.parse_args()

    record = json.loads(args.run.read_text(encoding="utf-8"))

    # The rows carry the labels they were scored against, so a restage cannot be
    # invalidated by the dataset moving — but a record whose digest no longer
    # matches is a record from a different measurement, and putting it in the same
    # table as today's runs is the mistake this whole week exists to undo.
    current = items_digest(args.items)
    if record["items_digest"] != current:
        raise SystemExit(
            f"this run was measured on items_digest {record['items_digest']}, and "
            f"{args.items} is now {current}. Re-measure rather than restage."
        )
    if record["scorer_version"] != SCORER_VERSION:
        raise SystemExit(
            f"this run was scored by {record['scorer_version']} and this is "
            f"{SCORER_VERSION}. The two are not comparable."
        )

    report = restage(record, args.stage)
    run_id = datetime.now().strftime("%Y%m%d-%H%M")
    new_record = run_record(
        report,
        record["implementation"],
        record["prompt_version"],
        record["split"],
        record["level"],
        run_id,
        digest=record["items_digest"],
        scorer_checked_on=record["scorer_checked_on"],
        stage=args.stage,
    )
    # What this run is, beyond its own numbers: which answers it re-scored, and the
    # fact that no call was made. Without the first, a table of five records has no
    # way to show that four of them share one set of answers.
    new_record["restaged_from"] = record["run_id"]
    new_record["api_calls"] = 0
    new_record["firing_rates"] = firing_rates(report)

    path = RUNS_DIR / f"{run_id}-{record['implementation']}-{args.stage}-{record['split']}.json"
    path.write_text(json.dumps(new_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{args.stage} over {record['run_id']}, n={len(report.outcomes)} (no calls)")
    print(f"  detection_accuracy      {_percent(report.detection_accuracy)}")
    print(f"  over_correction_rate    {_percent(report.over_correction_rate)}")
    rates = new_record["firing_rates"]
    print(f"  fired on already-natural {_percent(rates['on_already_natural'])}")
    print(f"  fired on needs-correction {_percent(rates['on_needs_correction'])}")
    gap = rates["gap_pt"]
    print(f"  gap                      {'not measured' if gap is None else f'{gap:+.1f}pt'}")
    print(f"\nrun record -> {path}")


def _percent(value: float | None) -> str:
    return "not measured" if value is None else f"{value:.1%}"


if __name__ == "__main__":
    main()
