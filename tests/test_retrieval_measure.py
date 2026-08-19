"""Tests for the two retrieval numbers, and for the rule that picks the threshold.

No model is loaded and no index is built: every test here runs over `Result` objects
written by hand, the same way the correction tests run over recorded answers. What
is being checked is arithmetic and discipline, and neither needs an embedding.

The rule for `score_min` is inverted — the recall floor is fixed in advance and the
threshold is what the data chooses — so the test that matters most is the one where
the rule CANNOT choose. On 2026-08-19 that is what happened, and a fallback that
quietly reported success would have turned a failed threshold into a passing one on
the way to the console.
"""

from __future__ import annotations

from evals.retrieval_measure import Outcome, abstention, choose_score_min, hit_rate
from retrieval.index import Result, grounding_article_ids


def result(article: str, score: float, section: int = 1) -> Result:
    return Result(
        chunk_id=f"{article}#{section}",
        article_id=article,
        heading="a heading",
        body="a body",
        score=score,
    )


def outcome(annotated: tuple[str, ...], *results: Result, item_id: str = "eval-001") -> Outcome:
    return Outcome(
        item_id=item_id,
        learner_sentence="スーパーに買い物します。",
        annotated=annotated,
        results=results,
    )


class TestGroundingIds:
    def test_keeps_rank_order_and_drops_repeats(self) -> None:
        # Two sections of one article are one citation. Naming it twice would make a
        # correction look better supported than it is.
        results = [
            result("grammar-001", 0.84, section=4),
            result("grammar-008", 0.83),
            result("grammar-001", 0.82, section=1),
        ]

        assert grounding_article_ids(results, 0.0) == ("grammar-001", "grammar-008")

    def test_applies_the_floor(self) -> None:
        results = [result("grammar-001", 0.84), result("grammar-008", 0.70)]

        assert grounding_article_ids(results, 0.80) == ("grammar-001",)

    def test_nothing_clears_a_floor_above_every_score(self) -> None:
        assert grounding_article_ids([result("grammar-001", 0.5)], 0.9) == ()


class TestChooseScoreMin:
    def test_picks_the_largest_floor_that_keeps_enough_items(self) -> None:
        outcomes = [
            outcome(("grammar-001",), result("grammar-001", 0.90)),
            outcome(("grammar-002",), result("grammar-002", 0.80)),
            outcome(("grammar-003",), result("grammar-003", 0.70)),
        ]

        # Two of three have to survive: 0.80 keeps exactly two, 0.90 keeps one.
        assert choose_score_min(outcomes, floor_items=2) == (0.80, 2)

    def test_the_answer_is_a_score_that_was_actually_observed(self) -> None:
        # Candidates are the observed scores plus 0, so the maximum is attained
        # rather than approached from below by an arbitrary epsilon.
        outcomes = [outcome(("grammar-001",), result("grammar-001", 0.8123))]

        value, _ = choose_score_min(outcomes, floor_items=1)
        assert value == 0.8123

    def test_items_with_no_annotation_do_not_count_towards_the_floor(self) -> None:
        # The denominator is the GROUNDED items. An item annotated `none` has no
        # article to keep, so including it would let a floor pass on items that
        # cannot fail.
        outcomes = [
            outcome(("grammar-001",), result("grammar-001", 0.90)),
            outcome((), result("grammar-005", 0.99)),
        ]

        assert choose_score_min(outcomes, floor_items=1) == (0.90, 1)

    def test_reports_reachable_items_when_no_floor_can_satisfy_the_rule(self) -> None:
        # THE 2026-08-19 CASE. Two of three annotated articles never enter the top
        # 3 at all, so no floor — not even 0 — can reach a requirement of 3. The
        # count reported alongside 0.0 must be the number an article was reachable
        # for, not the size of the sample.
        outcomes = [
            outcome(("grammar-001",), result("grammar-001", 0.90)),
            outcome(("grammar-002",), result("grammar-007", 0.88)),
            outcome(("grammar-003",), result("grammar-008", 0.87)),
        ]

        assert choose_score_min(outcomes, floor_items=3) == (0.0, 1)


class TestHitRate:
    def test_counts_an_annotated_article_anywhere_in_the_top_three(self) -> None:
        # Rank only. The score is never compared against score_min, so a hit at
        # 0.40 counts exactly as much as a hit at 0.90 — which is what stops the
        # published number from moving when the threshold is tuned.
        outcomes = [
            outcome(("grammar-001",), result("grammar-008", 0.9), result("grammar-001", 0.4)),
        ]

        assert hit_rate(outcomes) == (1.0, 1, 1)

    def test_items_annotated_none_leave_the_denominator(self) -> None:
        # Counting them as misses would report the reference's coverage as the
        # search's accuracy: there is no article for the search to have found.
        outcomes = [
            outcome(("grammar-001",), result("grammar-001", 0.9)),
            outcome((), result("grammar-005", 0.9)),
        ]

        assert hit_rate(outcomes) == (1.0, 1, 1)

    def test_a_sample_with_no_grounded_item_is_not_measured(self) -> None:
        # None rather than 0.0: an empty group was not measured, and 0% here would
        # read as a search that found nothing.
        assert hit_rate([outcome((), result("grammar-005", 0.9))]) == (None, 0, 0)


class TestAbstention:
    def test_counts_ungrounded_items_that_return_nothing_above_the_floor(self) -> None:
        outcomes = [
            outcome((), result("grammar-005", 0.50)),
            outcome((), result("grammar-006", 0.95)),
            outcome(("grammar-001",), result("grammar-001", 0.10)),
        ]

        assert abstention(outcomes, score_min=0.80) == (1, 2)

    def test_a_zero_floor_lets_everything_through(self) -> None:
        # Which is why the diagnostic says nothing at score_min = 0, and is
        # reported rather than interpreted.
        outcomes = [outcome((), result("grammar-005", 0.01))]

        assert abstention(outcomes, score_min=0.0) == (0, 1)
