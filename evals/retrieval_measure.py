"""Choosing `score_min`, and measuring `retrieval_hit_rate`. Two samples, never mixed.

THE TEN AND THE TWENTY ARE DIFFERENT QUESTIONS. The first block of
`evals/retrieval/worksheet.md` chooses the threshold; the second block measures the
hit rate. Choosing on the same items the number is published from would report how
well a threshold fits the data it was picked on. `--choose` therefore refuses to
look at the measurement sample, and `--measure` refuses to look at the threshold
sample, rather than leaving that to whoever runs them.

THE RULE FOR `score_min` WAS WRITTEN BEFORE THE DATA EXISTED and is copied here from
config/thresholds.toml, where it was fixed on 2026-08-13:

    score_min = the LARGEST value at which at least `recall_floor_items` of the
                grounded items in the threshold sample still have one of their
                annotated articles in the top 3 with a score at or above it.

Inverted on purpose. "The value that maximises recall" answers 0 whatever the data
says, because recall only rises as the floor falls — a criterion whose answer is
fixed in advance is not a criterion. So the recall floor is the part fixed in
advance, and the threshold is what the data chooses.

THE HIT RATE READS RANK ONLY. It never compares against `score_min`, so the
published number cannot be moved by tuning the threshold. That is why the two are
computed in one file and still never touch each other's inputs.

Run:  .venv/bin/python -m evals.retrieval_measure --choose
      .venv/bin/python -m evals.retrieval_measure --measure
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from config import threshold
from evals.dataset import ITEMS_PATH, Item, load_items
from evals.retrieval_kit import KIT_DIR, load_grounds
from retrieval.index import Result, search


@dataclass(frozen=True)
class Outcome:
    """One annotated item, and where its articles came back in the ranking."""

    item_id: str
    learner_sentence: str
    annotated: tuple[str, ...]
    results: tuple[Result, ...]

    @property
    def grounded(self) -> bool:
        """Whether an article was annotated for this item at all."""
        return bool(self.annotated)

    @property
    def best_annotated_score(self) -> float | None:
        """The score of the highest-ranked result naming an annotated article.

        None when no annotated article appears in the top 3 — which is a miss for
        the hit rate and, for the threshold, an item no floor can rescue.
        """
        scores = [r.score for r in self.results if r.article_id in self.annotated]
        return max(scores) if scores else None

    @property
    def hit(self) -> bool:
        """Rank only: is an annotated article among the top 3, at any score."""
        return self.best_annotated_score is not None


def sample_ids(block: str) -> list[str]:
    selection = json.loads((KIT_DIR / "selection.json").read_text(encoding="utf-8"))
    return list(selection[block])


def run_sample(
    ids: list[str], items: list[Item], grounds: dict[str, tuple[str, ...]]
) -> list[Outcome]:
    by_id = {item.id: item for item in items}
    outcomes: list[Outcome] = []
    for item_id in ids:
        item = by_id[item_id]
        outcomes.append(
            Outcome(
                item_id=item_id,
                learner_sentence=item.learner_sentence,
                annotated=grounds[item_id],
                results=tuple(search(item.learner_sentence)),
            )
        )
    return outcomes


def choose_score_min(outcomes: list[Outcome], floor_items: int) -> tuple[float, int]:
    """The largest floor at which `floor_items` grounded items still keep an article.

    Candidates are the scores actually observed, plus 0, so the maximum is attained
    rather than approached. Returns the value and how many items clear it, because
    "7 of 8 at 0.83" and "8 of 8 at 0.83" are different findings and the caller has
    to be able to print which one happened.
    """
    grounded = [o for o in outcomes if o.grounded]
    observed = sorted({r.score for o in outcomes for r in o.results} | {0.0}, reverse=True)
    for candidate in observed:
        kept = sum(
            1
            for o in grounded
            if o.best_annotated_score is not None and o.best_annotated_score >= candidate
        )
        if kept >= floor_items:
            return candidate, kept
    # No floor reaches the recall requirement. The answer is 0, and the count
    # reported with it is how many items an annotated article reached the top 3 at
    # all — NOT len(grounded). An item whose article never appears cannot be
    # "kept" by any floor, and reporting it as kept would turn a failed threshold
    # into a passing one on the way to the console.
    reachable = sum(1 for o in grounded if o.best_annotated_score is not None)
    return 0.0, reachable


def hit_rate(outcomes: list[Outcome]) -> tuple[float | None, int, int]:
    """Share of the GROUNDED items whose annotated article is in the top 3.

    The items annotated `none` are excluded from the denominator rather than
    counted as misses: nothing was annotated, so there is no article the search
    could have found, and counting them would report the reference's coverage as
    the search's accuracy.
    """
    grounded = [o for o in outcomes if o.grounded]
    if not grounded:
        return None, 0, 0
    hits = sum(1 for o in grounded if o.hit)
    return hits / len(grounded), hits, len(grounded)


def abstention(outcomes: list[Outcome], score_min: float) -> tuple[int, int]:
    """Of the items annotated `none`, how many returned nothing above the floor.

    Reported as a diagnostic, never used to choose: two items cannot separate
    anything, and picking a threshold to make both abstain would be fitting to two
    data points (config/thresholds.toml).
    """
    ungrounded = [o for o in outcomes if not o.grounded]
    quiet = sum(1 for o in ungrounded if all(r.score < score_min for r in o.results))
    return quiet, len(ungrounded)


def _print_outcomes(outcomes: list[Outcome]) -> None:
    for outcome in outcomes:
        best = outcome.best_annotated_score
        annotated = ", ".join(outcome.annotated) if outcome.annotated else "none"
        mark = "—" if not outcome.grounded else ("hit" if outcome.hit else "MISS")
        print(f"\n  {outcome.item_id}  {outcome.learner_sentence}")
        print(f"    annotated {annotated}   {mark}" + ("" if best is None else f"  @{best:.3f}"))
        for rank, result in enumerate(outcome.results, start=1):
            star = "*" if result.article_id in outcome.annotated else " "
            print(f"    {star}{rank}. {result.score:.3f}  {result.chunk_id}  {result.heading[:40]}")


BLOCKS: Final = {"choose": "threshold_sample", "measure": "measurement_sample"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--choose", action="store_true", help="pick score_min on the first ten")
    group.add_argument("--measure", action="store_true", help="hit rate on the other twenty")
    parser.add_argument("--items", type=Path, default=ITEMS_PATH)
    args = parser.parse_args()

    block = BLOCKS["choose" if args.choose else "measure"]
    items = load_items(args.items)
    grounds = load_grounds()
    outcomes = run_sample(sample_ids(block), items, grounds)

    if args.choose:
        floor_items = int(threshold("retrieval", "recall_floor_items"))
        value, kept = choose_score_min(outcomes, floor_items)
        grounded = [o for o in outcomes if o.grounded]
        print(f"threshold sample: {len(outcomes)} items, {len(grounded)} with an article")
        print(f"rule: largest floor keeping >= {floor_items} of {len(grounded)}")
        print(f"\n  score_min = {value:.4f}   ({kept} of {len(grounded)} kept)")
        quiet, total = abstention(outcomes, value)
        print(f"  diagnostic: {quiet} of {total} `none` items return nothing at or above it")
        _print_outcomes(outcomes)
        print("\nWrite this into config/thresholds.toml with the measurement beside it.")
        return

    rate, hits, total = hit_rate(outcomes)
    print(f"measurement sample: {len(outcomes)} items, {total} with an article")
    shown = "not measured" if rate is None else f"{rate:.1%}"
    print(f"\n  retrieval_hit_rate = {shown}  ({hits}/{total}, rank only, top 3)")
    _print_outcomes(outcomes)


if __name__ == "__main__":
    main()
