"""Tests for the second rater's kit.

`rater_agreement` is measured once, on 8/9, at the only Minna Shuugou meeting in
August. There is no second attempt, so the failures pinned here are the ones that
would not be visible on the day and could not be repaired afterwards:

  - a kit built from `test`, which would burn the split that the published numbers
    depend on (docs/ja/glossary.md §7),
  - an item nobody can grade — the system said the sentence was fine, so there is
    no correction and no reason for the §6 scale to look at — which would show up
    as two blanks and then be counted as agreement,
  - the dataset's own answer leaking onto the form, which turns the number into a
    reading comprehension test,
  - a kit that cannot be regenerated from the run record it came from, leaving the
    returned ratings attached to nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dialogue.scenes import politeness_floor, scene_brief
from evals.dataset import Item, save_items
from evals.rater_kit import (
    KIT_SIZE,
    SCALE,
    agreement,
    kit_markdown,
    kit_record,
    scoring_template,
    select,
)

SCENE_ORDER = [
    "greeting",
    "self_introduction",
    "thanks",
    "simple_request",
    "delay_notice",
    "workplace_keigo",
]


def make_result(
    item_id: str,
    scene: str,
    predicted: bool = True,
    corrected: str | None = "おはようございます。",
    reason: str | None = "The polite morning greeting is a fixed phrase.",
) -> dict[str, Any]:
    return {
        "id": item_id,
        "scene": scene,
        "learner_sentence": "おはようです。",
        "expected": True,
        "predicted": predicted,
        "format_compliant": True,
        "format_problems": [],
        "japanese_left_unquoted": False,
        "attempts": 1,
        "corrected_sentence": corrected,
        "reason_en": reason,
    }


def make_record(results: list[dict[str, Any]], split: str = "dev") -> dict[str, Any]:
    return {
        "run_id": "20260808-1000",
        "implementation": "baseline",
        "model": "gemini/gemini-2.5-flash",
        "prompt_version": "baseline-v1",
        "scorer_version": "score-v1",
        "n": len(results),
        "split": split,
        "level": "beginner",
        "results": results,
    }


def write_items(path: Path, results: list[dict[str, Any]], split: str = "dev") -> Path:
    """An items.json holding exactly the ids in `results`, all on one split."""
    save_items(
        [
            Item(
                id=result["id"],
                scene=result["scene"],
                learner_sentence=result["learner_sentence"],
                needs_correction=True,
                corrected_sentence="おはようございます。",
                reason_en="A fixed phrase.",
                split=split,  # type: ignore[arg-type]
            )
            for result in results
        ],
        path,
    )
    return path


def gradable_run(per_scene: int = 5) -> list[dict[str, Any]]:
    return [
        make_result(f"eval-{scene_no * 100 + number:03d}", scene)
        for scene_no, scene in enumerate(SCENE_ORDER)
        for number in range(per_scene)
    ]


def test_a_test_split_run_is_refused(tmp_path: Path) -> None:
    results = gradable_run()
    record = make_record(results, split="test")
    items = write_items(tmp_path / "items.json", results, split="test")

    with pytest.raises(ValueError, match="dev run"):
        select(record, 20, items)


def test_items_the_system_passed_are_never_offered_for_grading(tmp_path: Path) -> None:
    """A "this sentence is fine" verdict has nothing the §6 scale can grade."""
    results = gradable_run()
    results[0]["predicted"] = False
    items = write_items(tmp_path / "items.json", results)

    graded = {selection.id for selection in select(make_record(results), 20, items)}

    assert results[0]["id"] not in graded


def test_a_correction_missing_its_sentence_or_reason_is_skipped(tmp_path: Path) -> None:
    results = gradable_run()
    results[0]["corrected_sentence"] = None
    results[1]["reason_en"] = None
    items = write_items(tmp_path / "items.json", results)

    graded = {selection.id for selection in select(make_record(results), 20, items)}

    assert results[0]["id"] not in graded
    assert results[1]["id"] not in graded


def test_every_scene_reaches_the_form(tmp_path: Path) -> None:
    """The politeness floor is what two raters most easily read differently.

    Taking the first 20 in run order would hand over `greeting` and
    `self_introduction` only, and agreement would then say nothing about tiers B
    and C (docs/ja/glossary.md §2).
    """
    results = gradable_run()
    items = write_items(tmp_path / "items.json", results)

    selections = select(make_record(results), 20, items)

    assert {selection.scene for selection in selections} == set(SCENE_ORDER)
    per_scene = [sum(1 for s in selections if s.scene == scene) for scene in SCENE_ORDER]
    assert max(per_scene) - min(per_scene) <= 1


def test_selection_is_reproducible(tmp_path: Path) -> None:
    """The kit is printed and carried to a meeting; the ratings come back by id."""
    results = gradable_run()
    items = write_items(tmp_path / "items.json", results)
    record = make_record(results)

    first = [selection.id for selection in select(record, 20, items)]
    second = [selection.id for selection in select(record, 20, items)]

    assert first == second
    assert [selection.kit_no for selection in select(record, 20, items)] == list(range(1, 21))


def test_too_few_gradable_items_fails_loudly(tmp_path: Path) -> None:
    """Silently handing over 14 items would divide the agreement by the wrong n."""
    results = gradable_run(per_scene=2)
    items = write_items(tmp_path / "items.json", results)

    with pytest.raises(ValueError, match="only 12"):
        select(make_record(results), 20, items)


def test_an_id_outside_dev_stops_the_kit(tmp_path: Path) -> None:
    """The run record says dev; this checks the items themselves agree."""
    results = gradable_run()
    items = write_items(tmp_path / "items.json", results, split="test")

    with pytest.raises(ValueError, match="not a dev item"):
        select(make_record(results), 20, items)


def test_a_test_item_is_caught_even_when_nobody_would_have_graded_it(tmp_path: Path) -> None:
    """The guard runs over every result, not only the gradable ones.

    A record that mixes splits is a broken record. Checking only the items that
    reach the rater would let it through whenever the stray item happened to be one
    the system passed as fine.
    """
    results = gradable_run()
    results[0]["predicted"] = False
    write_items(tmp_path / "items.json", results)
    stray = json.loads((tmp_path / "items.json").read_text(encoding="utf-8"))
    stray[0]["split"] = "test"
    (tmp_path / "items.json").write_text(json.dumps(stray, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="not a dev item"):
        select(make_record(results), 20, tmp_path / "items.json")


def test_the_form_never_shows_the_datasets_own_answer(tmp_path: Path) -> None:
    """Otherwise the number measures how well the rater can read the dataset."""
    results = gradable_run()
    items = write_items(tmp_path / "items.json", results)
    kit = kit_record(make_record(results), select(make_record(results), 20, items))

    for item in kit["items"]:
        assert set(item) == {
            "kit_no",
            "id",
            "scene",
            "learner_sentence",
            "corrected_sentence",
            "reason_en",
        }
    assert "expected" not in json.dumps(kit)


def test_the_printed_form_carries_the_whole_scale(tmp_path: Path) -> None:
    """Every grade has to be tickable on every item, or it cannot be given."""
    results = gradable_run()
    items = write_items(tmp_path / "items.json", results)
    kit = kit_record(make_record(results), select(make_record(results), 20, items))

    printed = kit_markdown(kit)

    for label, meaning in SCALE.values():
        assert meaning in printed
        assert printed.count(f"☐ {label}") == kit["n"]
    assert kit["kit_id"] in printed


def test_the_printed_form_shows_everything_the_scale_needs(tmp_path: Path) -> None:
    """The rater grades the correction AND the reason (§6), against the situation.

    Without this, deleting the reason from the rendered page leaves every other test
    passing while the form no longer supports the scale it is printed with.
    """
    results = gradable_run()
    results[0]["learner_sentence"] = "おはようです。"
    results[0]["corrected_sentence"] = "おはようございます。"
    results[0]["reason_en"] = "The polite morning greeting is a fixed phrase."
    items = write_items(tmp_path / "items.json", results)
    kit = kit_record(make_record(results), select(make_record(results), 20, items))

    printed = kit_markdown(kit)

    for item in kit["items"]:
        assert item["learner_sentence"] in printed
        assert item["corrected_sentence"] in printed
        assert item["reason_en"] in printed
    # The exact situation string the model was given, not the scene name.
    assert scene_brief("greeting")[0] in printed
    assert politeness_floor("greeting")[1] in printed


def test_the_kit_records_the_level_the_reasons_appeal_to(tmp_path: Path) -> None:
    """Several real reasons say "given the N5 level"; the form has to say it too."""
    results = gradable_run()
    items = write_items(tmp_path / "items.json", results)

    kit = kit_record(make_record(results), select(make_record(results), 20, items))

    assert kit["level"] == "beginner"
    assert "beginner" in kit_markdown(kit)


def make_form(
    rater: str, ratings: list[str | None] | None = None, kit_id: str = "k1"
) -> dict[str, Any]:
    """A filled-in form of the real size. Short forms are themselves an error."""
    graded = ratings if ratings is not None else ["valid"] * KIT_SIZE
    return {
        "kit_id": kit_id,
        "rater": rater,
        "scale": list(SCALE),
        "ratings": [
            {"kit_no": number, "id": f"eval-{number:03d}", "rating": rating, "note": ""}
            for number, rating in enumerate(graded, start=1)
        ],
    }


def grades(*overrides: str | None) -> list[str | None]:
    """20 grades, with the first few replaced by the ones given."""
    filled: list[str | None] = ["valid"] * KIT_SIZE
    for index, rating in enumerate(overrides):
        filled[index] = rating
    return filled


def test_agreement_counts_matching_grades_and_names_the_rest() -> None:
    mine = make_form("jun", grades("valid", "valid", "insufficient", "wrong"))
    theirs = make_form("second", grades("valid", "wrong", "insufficient", "valid"))

    rate, disagreed = agreement(mine, theirs)

    assert rate == 0.9
    assert disagreed == ["eval-002", "eval-004"]


def test_an_ungraded_item_is_not_silently_agreement() -> None:
    """The failure this module exists to prevent: two blanks reading as a match."""
    mine = make_form("jun", grades("valid", None))
    theirs = make_form("second", grades("valid", None))

    with pytest.raises(ValueError, match="not one of"):
        agreement(mine, theirs)


def test_a_blank_string_is_refused_the_same_way_as_a_missing_grade() -> None:
    """`is None` alone would miss this, and the template ships `note: ""` alongside."""
    mine = make_form("jun", grades("valid", ""))
    theirs = make_form("second", grades("valid", ""))

    with pytest.raises(ValueError, match="not one of"):
        agreement(mine, theirs)


def test_a_grade_copied_off_the_paper_form_in_capitals_is_refused() -> None:
    """The printed tick boxes read `Valid`; the file wants `valid`.

    Left unchecked this scores every item as a disagreement and reports a
    catastrophic-looking `rater_agreement` that is purely a transcription artefact.
    """
    mine = make_form("jun", grades("Valid"))
    theirs = make_form("second", grades("valid"))

    with pytest.raises(ValueError, match="'Valid'"):
        agreement(mine, theirs)


def test_forms_covering_different_items_are_refused() -> None:
    """Otherwise the denominator is whichever form was read first."""
    mine = make_form("jun")
    theirs = make_form("second")
    theirs["ratings"][0]["id"] = "eval-999"

    with pytest.raises(ValueError, match="different items"):
        agreement(mine, theirs)


def test_a_short_form_is_refused() -> None:
    """19 items rated as if they were 20 is a wrong number, not a smaller one."""
    mine = make_form("jun")
    mine["ratings"].pop()

    with pytest.raises(ValueError, match="19 items graded"):
        agreement(mine, make_form("second"))


def test_a_duplicated_id_is_refused() -> None:
    """Two rows collapse into one, silently shrinking the denominator."""
    mine = make_form("jun")
    mine["ratings"][1]["id"] = mine["ratings"][0]["id"]

    with pytest.raises(ValueError, match="appears twice"):
        agreement(mine, make_form("second"))


def test_two_forms_from_the_same_rater_are_refused() -> None:
    mine = make_form("jun")
    also_mine = make_form("jun", grades("wrong"))

    with pytest.raises(ValueError, match="same rater"):
        agreement(mine, also_mine)


def test_forms_for_different_kits_are_refused() -> None:
    mine = make_form("jun", kit_id="k1")
    theirs = make_form("second", kit_id="k2")

    with pytest.raises(ValueError, match="different kits"):
        agreement(mine, theirs)


def test_the_blank_form_holds_no_grades(tmp_path: Path) -> None:
    """Sealed before 8/9: a template that arrived pre-filled would be worthless."""
    results = gradable_run()
    items = write_items(tmp_path / "items.json", results)
    kit = kit_record(make_record(results), select(make_record(results), 20, items))

    template = scoring_template(kit, "jun")

    assert len(template["ratings"]) == 20
    assert all(row["rating"] is None for row in template["ratings"])
    assert [row["id"] for row in template["ratings"]] == [item["id"] for item in kit["items"]]
