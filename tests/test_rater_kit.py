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
from evals.dataset import ITEMS_PATH, Item, load_items, save_items
from evals.rater_kit import (
    KIT_SIZE,
    SCALE,
    agreement,
    build_kit,
    kit_markdown,
    kit_record,
    refuse_if_graded,
    scoring_template,
    select,
    whatsapp_message,
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


def built_kit(tmp_path: Path) -> dict[str, Any]:
    results = gradable_run()
    items = write_items(tmp_path / "items.json", results)
    return kit_record(make_record(results), select(make_record(results), 20, items))


def test_the_sent_message_shows_everything_the_scale_needs(tmp_path: Path) -> None:
    """The chat version grades the same thing as the paper version, or neither counts.

    The two are read by different people at different times and both feed one number,
    so the message losing a reason — the half of §6 the paper form is careful to
    print — would show up as agreement about corrections nobody was shown.
    """
    kit = built_kit(tmp_path)

    sent = whatsapp_message(kit, "2026-08-16")

    for item in kit["items"]:
        assert item["learner_sentence"] in sent
        assert item["corrected_sentence"] in sent
        assert item["reason_en"] in sent
    for _, meaning in SCALE.values():
        assert meaning in sent
    assert scene_brief("greeting")[0] in sent
    assert politeness_floor("greeting")[1] in sent
    assert "2026-08-16" in sent


def test_the_sent_message_asks_for_the_grades_the_scoring_file_accepts(tmp_path: Path) -> None:
    """Lower case, and one numbered blank per item.

    `_graded` refuses "Valid" — the capitalisation on the paper tick boxes. Over chat
    the reply is pasted straight into the scoring file, so anything the message asks
    for that `agreement` would then reject is a transcription step reintroduced for
    no reason.
    """
    kit = built_kit(tmp_path)

    sent = whatsapp_message(kit, "2026-08-16")
    template = sent.split("Copy from here")[1]

    for key, (label, _) in SCALE.items():
        assert key in template
        assert label not in template
    for item in kit["items"]:
        assert f"\n{item['kit_no']}:" in template


def test_a_free_text_reply_is_never_what_the_message_asks_for(tmp_path: Path) -> None:
    """The twenty blanks are the point: prose would be assigned to grades by hand.

    That assignment is done by the same person whose own grades are being compared,
    which makes part of `rater_agreement` a measure of how they read the other rater.
    """
    kit = built_kit(tmp_path)

    sent = whatsapp_message(kit, "2026-08-16")

    assert sent.rstrip().endswith(f"{kit['n']}:")
    assert sum(line.strip().endswith(":") and line[0].isdigit() for line in sent.splitlines()) == 20


def test_both_forms_carry_the_convention_for_the_cases_the_grades_miss(tmp_path: Path) -> None:
    """§6 requires the same convention on the paper form and in the message.

    Two of the twenty items needed no correction and one was corrected further than
    it needed to be, and the three grades name neither case. The author graded all
    three before sealing; a second rater who is not told the convention disagrees on
    them for a reason that is not a difference of judgement — which is the one thing
    `rater_agreement` must not measure. Nothing else asserts this, so dropping the
    paragraph from either renderer is otherwise a silent change.
    """
    kit = built_kit(tmp_path)

    printed = kit_markdown(kit)
    sent = whatsapp_message(kit, "2026-08-16")

    for rendered in (printed, sent):
        assert "already correct and needed no change at all" in rendered
        assert "changed more than that" in rendered
    assert "*Insufficient*" in printed and "*Wrong*" in printed
    assert "*insufficient*" in sent and "*wrong*" in sent


def test_the_message_never_names_a_number_of_grades_the_scale_does_not_have(
    tmp_path: Path,
) -> None:
    """The paper form derives the grades from SCALE; the message has to as well.

    §6 was nearly given a fourth box and was settled by convention instead, so a
    fourth grade is a live possibility rather than a hypothetical. Written out by
    hand, the message would keep saying "three words" next to four of them and keep
    offering three in the reply template — a form that contradicts itself, sent to
    someone who cannot ask.
    """
    kit = built_kit(tmp_path)

    sent = whatsapp_message(kit, "2026-08-16")

    assert "three words" not in sent
    template = sent.split("Copy from here")[1]
    for key in SCALE:
        assert key in template


def test_rebuilding_a_kit_will_not_erase_grades_already_on_a_form(tmp_path: Path) -> None:
    """`--run` reprints the kit and both blank forms. The grades are not its to touch.

    This happened: the kit was rebuilt after a wording fix and wrote nulls over the
    author's twenty grades, which existed in no other copy and were not yet
    committed. `rater_agreement` needs both forms, one of them is filled in by hand
    before the other is sent, and the window between those two events is exactly when
    the kit gets reprinted.
    """
    kit = built_kit(tmp_path)
    form = tmp_path / "kit-jun.json"
    filled = scoring_template(kit, "jun")
    filled["ratings"][0]["rating"] = "valid"
    form.write_text(json.dumps(filled, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SystemExit, match="would be erased"):
        refuse_if_graded(form)

    assert json.loads(form.read_text(encoding="utf-8"))["ratings"][0]["rating"] == "valid"


def test_rebuilding_the_whole_kit_stops_before_it_writes_anything(tmp_path: Path) -> None:
    """The guard has to be wired into the command, not merely exist.

    The accident was `--run` erasing a filled-in form, so a test that calls
    `refuse_if_graded` directly leaves the failing path — the command forgetting to
    call it — green. Rebuilding also has to be all-or-nothing: a kit half rewritten
    around the one file it would not touch is a kit whose printed form and grades
    describe different items.
    """
    results = gradable_run()
    items = write_items(tmp_path / "items.json", results)
    record = make_record(results)
    out = tmp_path / "rater"
    build_kit(record, items, out, ["jun", "second"])

    kit_json = (out / "20260808-1000-rater-kit.json").read_text(encoding="utf-8")
    (out / "20260808-1000-rater-kit.json").write_text("{}", encoding="utf-8")
    form = out / "20260808-1000-rater-kit-jun.json"
    filled = json.loads(form.read_text(encoding="utf-8"))
    filled["ratings"][0]["rating"] = "valid"
    form.write_text(json.dumps(filled, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SystemExit, match="would be erased"):
        build_kit(record, items, out, ["jun", "second"])

    assert json.loads(form.read_text(encoding="utf-8"))["ratings"][0]["rating"] == "valid"
    # Untouched too: the refusal came before the first write, not after two of them.
    assert (out / "20260808-1000-rater-kit.json").read_text(encoding="utf-8") == "{}"
    assert kit_json  # the real kit was written the first time round


def test_an_untouched_blank_form_does_not_block_a_rebuild(tmp_path: Path) -> None:
    """Otherwise a half-built kit could never be rebuilt without deleting files."""
    kit = built_kit(tmp_path)
    form = tmp_path / "kit-second.json"
    form.write_text(
        json.dumps(scoring_template(kit, "second"), ensure_ascii=False), encoding="utf-8"
    )

    refuse_if_graded(form)


def _bare(text: str) -> str:
    """Text with the punctuation and quoting that a citation drops."""
    return "".join(ch for ch in text if ch not in "。、？！「」『』・…　 \n\t")


def test_a_run_record_passed_as_a_kit_is_refused_by_name(tmp_path: Path) -> None:
    """Both are JSON under evals/ holding the same ids; --whatsapp takes only one."""
    with pytest.raises(ValueError, match="not a rater kit"):
        whatsapp_message(make_record(gradable_run()), "2026-08-16")


def test_no_form_quotes_an_evaluation_item_in_its_own_scaffolding(tmp_path: Path) -> None:
    """The wording around the items must cite no sentence the dataset has labelled.

    Both forms print the situation and the politeness floor so the rater can judge
    "would a native say this here" (the day 6 finding: 「良い一日。」 → 「いってらっしゃい！」
    is only right because the neighbour is leaving). On 8/9 the tier B floor grew
    worked examples — 「お仕事、何？」 needs correcting, 「はじめまして」 is fine — and each
    one is an evaluation item with the dataset's verdict attached. One of them,
    eval-017, was item 20 of the kit already built, so its own answer was printed
    four lines above it, and another was from `test`.

    Checked by rendering a kit whose items carry placeholder text, which leaves only
    the scaffolding: anything from `items.json` that survives got there through the
    form, not through the item being graded.

    Compared with the punctuation stripped, because a rule is written about a
    sentence rather than quoting one — 「はじめまして」 in prose against 「はじめまして。」 in
    the dataset. That is the same disclosure and it is the likelier spelling of it:
    the first version of this test matched exactly and let the sentence back in.
    """
    results = gradable_run()
    items = write_items(tmp_path / "items.json", results)
    kit = kit_record(make_record(results), select(make_record(results), 20, items))
    for item in kit["items"]:
        item["learner_sentence"] = f"__learner_{item['kit_no']}__"
        item["corrected_sentence"] = f"__corrected_{item['kit_no']}__"
        item["reason_en"] = f"__reason_{item['kit_no']}__"

    scaffolding = _bare(kit_markdown(kit) + whatsapp_message(kit, "2026-08-16"))

    for real in load_items(ITEMS_PATH):
        for field, sentence in (
            ("learner sentence", real.learner_sentence),
            ("own answer", real.corrected_sentence),
            ("reason", real.reason_en),
        ):
            if sentence:
                assert _bare(sentence) not in scaffolding, (
                    f"{real.id} ({real.split}): the {field} is in the form the rater reads"
                )


def test_a_test_split_kit_is_never_rendered_for_sending(tmp_path: Path) -> None:
    """Paper stayed in the room. A message does not come back.

    `select` already refuses a test run, so this is the same rule one step later —
    at the only point where items leave the project entirely (docs/ja/glossary.md §7).
    """
    kit = built_kit(tmp_path)
    kit["split"] = "test"

    with pytest.raises(ValueError, match="only a dev kit"):
        whatsapp_message(kit, "2026-08-16")


def test_the_sent_message_reproduces_the_reason_verbatim(tmp_path: Path) -> None:
    """The reason is the object being graded, so it is not reflowed to render better."""
    kit = built_kit(tmp_path)
    kit["items"][0]["reason_en"] = "Use *で* here, not 'に' — it marks _where_ you act."

    sent = whatsapp_message(kit, "2026-08-16")

    assert "Use *で* here, not 'に' — it marks _where_ you act." in sent


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
