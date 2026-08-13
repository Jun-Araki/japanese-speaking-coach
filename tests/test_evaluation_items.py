"""The machine check on data/evaluation/items.json.

The dataset is the deliverable of week 1 and the thing every published number is
computed from. Counting 120 items by eye is how a dataset ends up 89:31, and a
dataset that is quietly 89:31 does not fail anywhere — it just makes
`over_correction_rate` a slightly different number than the README claims.

So the composition is asserted here rather than checked by reading:

  - 120 items, 90 labelled `true` and 30 `false` (docs/ja/glossary.md §5, whose
    metric definitions name those two denominators),
  - dev 80 / test 40 (§7), and 2:1 within every scene — a split that is 2:1
    overall but lopsided per scene makes `detection_accuracy` move with which
    scenes happened to land in test,
  - **the 60 items labelled on day 3 keep the split they were given on day 3.**
    Re-assigning the whole dataset when the second batch arrives would move test
    items into dev after a baseline had already been measured on them. Nothing
    would fail; the day 4 run record would simply stop describing the data it was
    run on.

The last one is why the day-3 assignment is pinned as a literal below instead of
being recomputed. A rule can be changed by accident; a list of 20 ids cannot.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dialogue.scenes import SCENES
from evals.dataset import ITEMS_PATH, Item, counts_by_scene, load_items

# What the dataset is finished at, per PLAN.md and docs/ja/glossary.md §5.
#
# 91/29, not the 90/30 fixed on day 3. eval-052 「部長、話したいことあります。」 was
# relabelled `true` on 2026-08-13: preparing the retrieval annotations surfaced that
# it contradicted data/grammar/grammar-002, which requires 「が」 before 「あります」 in
# careful speech to a manager, and eval-054 「この件、確認必要です。」 is the same
# omission labelled `true`. Jun, a native speaker, settled it on the article's side.
# The item is `dev`, so no test-split denominator moves and the 8/11 held-out
# measurements are unaffected — but `items_digest` does, and the runs either side of
# it are told apart by that digest and by this comment.
TOTAL = 120
NEEDS_CORRECTION = 91
NATURAL = 29
DEV = 80
TEST = 40

# The 20 of eval-001..eval-060 that went to test on day 3 (2026-08-05), measured on
# day 4 and recorded in evals/runs/20260806-0724-baseline-test.json. Every other
# item in that range is dev. Not derived from assign_splits on purpose: this is the
# record of what was actually measured, and it has to survive a change to the rule.
DAY3_TEST_IDS = frozenset(
    {
        "eval-003",
        "eval-006",
        "eval-007",
        "eval-011",
        "eval-015",
        "eval-018",
        "eval-021",
        "eval-024",
        "eval-027",
        "eval-030",
        "eval-033",
        "eval-037",
        "eval-040",
        "eval-041",
        "eval-045",
        "eval-049",
        "eval-051",
        "eval-054",
        "eval-057",
        "eval-060",
    }
)
DAY3_IDS = frozenset(f"eval-{number:03d}" for number in range(1, 61))


@pytest.fixture(scope="module")
def items() -> list[Item]:
    """The real dataset. This suite is about the data, not about the loader."""
    return load_items()


def test_the_dataset_has_120_items(items: list[Item]) -> None:
    assert len(items) == TOTAL


def test_the_labels_are_90_to_30(items: list[Item]) -> None:
    """Both metric definitions in §5 name these denominators explicitly."""
    needs = sum(1 for item in items if item.needs_correction)
    assert (needs, len(items) - needs) == (NEEDS_CORRECTION, NATURAL)


def test_the_splits_are_80_to_40(items: list[Item]) -> None:
    dev = sum(1 for item in items if item.split == "dev")
    assert (dev, len(items) - dev) == (DEV, TEST)


def test_ids_are_unique(items: list[Item]) -> None:
    """A duplicate id makes a run record ambiguous about which item it scored."""
    ids = [item.id for item in items]
    assert len(set(ids)) == len(ids)


def test_every_scene_is_one_of_the_six(items: list[Item]) -> None:
    assert {item.scene for item in items} <= set(SCENES)


def test_every_scene_is_present(items: list[Item]) -> None:
    """A scene with no items is a scene the numbers say nothing about."""
    assert {item.scene for item in items} == set(SCENES)


def test_a_natural_item_carries_no_correction(items: list[Item]) -> None:
    """A "you could also say" on a `false` item teaches the scorer to expect one."""
    for item in items:
        if not item.needs_correction:
            assert item.corrected_sentence is None, item.id
            assert item.reason_en is None, item.id


def test_an_item_needing_correction_carries_both_fields(items: list[Item]) -> None:
    for item in items:
        if item.needs_correction:
            assert item.corrected_sentence, item.id
            assert item.reason_en, item.id


def test_a_correction_is_not_the_sentence_it_corrects(items: list[Item]) -> None:
    """Seen during the day 5 audit: a repair that changes nothing is a mislabel."""
    for item in items:
        if item.needs_correction:
            assert item.corrected_sentence != item.learner_sentence, item.id


def test_the_split_is_two_to_one_inside_every_scene(items: list[Item]) -> None:
    """2:1 overall but lopsided per scene makes the numbers move with the draw."""
    for scene, row in counts_by_scene(items).items():
        assert row["total"] > 0, scene
        expected_test = round(row["total"] / 3)
        assert abs(row["test"] - expected_test) <= 1, (scene, row)


def test_day_3_items_keep_the_split_they_were_measured_on(items: list[Item]) -> None:
    """The day 4 baseline was measured on exactly these 20 ids.

    If this fails after the second batch is merged, the second batch was split by
    re-assigning the whole dataset instead of by continuing from item 61.
    """
    assigned = {item.id: item.split for item in items if item.id in DAY3_IDS}

    assert set(assigned) == DAY3_IDS
    assert {item_id for item_id, split in assigned.items() if split == "test"} == DAY3_TEST_IDS


def test_a_missing_required_key_raises(tmp_path: Path) -> None:
    """load_items refuses a malformed item rather than skipping it.

    Skipping would shrink a denominator without shrinking the reported `n`.
    """
    path = tmp_path / "items.json"
    complete = {
        "id": "eval-001",
        "scene": "greeting",
        "learner_sentence": "おはようです。",
        "needs_correction": True,
        "corrected_sentence": "おはようございます。",
        "reason_en": "A fixed phrase.",
        "split": "dev",
    }
    for missing in ("id", "scene", "learner_sentence", "needs_correction", "split"):
        path.write_text(
            json.dumps([{k: v for k, v in complete.items() if k != missing}]),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match=missing):
            load_items(path)


def test_the_file_is_where_everything_expects_it(items: list[Item]) -> None:
    assert ITEMS_PATH.exists()
