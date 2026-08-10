"""The second rater's kit: which 20 items get scored, and the form they go on.

`rater_agreement` (docs/ja/glossary.md §5) is the share of 20 items where this
project's author and a second Japanese native speaker, scoring independently, give
the same verdict on the §6 scale. It measures whether the SCALE reads the same way
to two people. How good the corrections are is a different number
(`correction_validity`, 40 items) and is not what this file is for.

Three decisions are fixed here, because each one can void the number quietly:

  - **The 20 come from `dev`.** §5 does not say which split, and `test` looks like
    the natural answer since that is where the published figures come from. It is
    the wrong one. Scoring an item by hand means reading it, and week 2 tunes
    prompts against everything the author has read; 20 test items read now turn
    every later test measurement into self-assessment (§7). Agreement is a property
    of the scale, so dev carries it just as well.
  - **Only items the implementation actually corrected.** The §6 scale rates a
    corrected sentence and its English reason. An item the system passed as fine
    has neither, so it cannot be scored — it would leave a blank in both forms and
    then count as agreement.
  - **The rater is shown neither the dataset's label nor the reference
    correction.** They get the learner's sentence, the system's correction, the
    system's reason, and the situation the system was told it was in. Showing them
    what the dataset expects would measure how well they can read the dataset.

Build the kit:  .venv/bin/python -m evals.rater_kit --run evals/runs/<run>-baseline-dev.json
Send it:        .venv/bin/python -m evals.rater_kit --whatsapp evals/rater/<kit>.json \
                                                    --reply-by 2026-08-16
Score it:       .venv/bin/python -m evals.rater_kit --score evals/rater/<kit>-jun.json \
                                                            evals/rater/<kit>-second.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from dialogue.scenes import SCENES, politeness_floor, scene_brief
from evals.dataset import ITEMS_PATH, load_items

RATER_DIR: Final = Path("evals/rater")

# The `level` identifier is for the run record; this is how it reads to someone who
# has never seen the app. Nothing on the printed form should need decoding.
LEVEL_WORDING: Final[dict[str, str]] = {
    "beginner": "complete beginner",
    "upper_beginner": "beginner",
    "intermediate": "intermediate",
}

# §6 has three grades and `correction_validity` counts only the first. The English
# wording is what the second rater reads on paper, so it is part of the measurement
# rather than a label in the interface: two raters who read "insufficient"
# differently produce a low agreement that says nothing about the corrections.
SCALE: Final[dict[str, tuple[str, str]]] = {
    "valid": (
        "Valid",
        "The corrected sentence is what a native speaker would actually say here, "
        "AND the English reason is accurate and useful to a beginner.",
    ),
    "insufficient": (
        "Insufficient",
        "The correction itself is acceptable, but the reason is vague or generic "
        "and does not explain what was actually wrong.",
    ),
    "wrong": (
        "Wrong",
        "The corrected sentence is unnatural or changes the meaning, OR the reason "
        "states something that is factually untrue.",
    ),
}

# The scale was written assuming something needed correcting, and the first twenty
# items found two ways for that assumption to fail. Undefined, each splits raters in
# the same shape — the corrected sentence is natural, which reads as Valid; the
# correction went further than it had to, which reads as Wrong — so the disagreement
# would be a fault in the scale rather than a difference of judgement. Settled by
# convention instead of two more boxes, because the form is already printed
# (docs/ja/glossary.md §6).
#
#   - Nothing needed correcting at all: two of the twenty.
#   - Something did, and the AI supplied it and then also swapped a verb: one more.
#
# Which items, and how they were graded, is deliberately not written down here or in
# §6. This file is in a public repository and the second rater has its address; the
# kit numbers plus the author's own grades are exactly the agreement being measured.
#
# Rendered rather than stored, because the two forms name the grades differently: the
# paper form capitalises to match its tick boxes, and the message keeps the lower case
# it asks to be sent back. §6 requires both to say the same thing, so only the grade
# names may vary.
_SCALE_NOTE_TEMPLATE: Final = (
    "{open}If the learner's sentence was already correct and needed no change at "
    "all{close}, answer {insufficient} — unless the AI's version is unnatural or means "
    "something different, which is {wrong}.\n"
    "{open}If it did need correcting but the AI changed more than that{close}, the "
    "necessary part being right is enough for {insufficient}; answer {wrong} only if "
    "what it added makes the sentence unnatural or no longer a version of what the "
    "learner said."
)


def scale_note(insufficient: str, wrong: str, open: str = "**", close: str = "**") -> str:
    """§6's convention for the cases the three grades do not cover, in one wording."""
    return _SCALE_NOTE_TEMPLATE.format(
        open=open, close=close, insufficient=insufficient, wrong=wrong
    )


SCALE_NOTE: Final = scale_note("*Insufficient*", "*Wrong*")

# Fixed at 20 by the definition of `rater_agreement` in docs/ja/glossary.md §5, and
# separately by the day: this is 30 minutes of a stranger's time at a meeting that
# happens once in August. It is not a tuning knob, so it is not on the command line
# — a kit built at any other size is not the metric the README will name.
KIT_SIZE: Final = 20


@dataclass(frozen=True)
class Selection:
    """One item as the rater sees it, plus the ids needed to score it later."""

    kit_no: int
    id: str
    scene: str
    learner_sentence: str
    corrected_sentence: str
    reason_en: str

    def to_json(self) -> dict[str, Any]:
        return {
            "kit_no": self.kit_no,
            "id": self.id,
            "scene": self.scene,
            "learner_sentence": self.learner_sentence,
            "corrected_sentence": self.corrected_sentence,
            "reason_en": self.reason_en,
        }


def select(
    record: dict[str, Any], size: int = KIT_SIZE, items_path: Path = ITEMS_PATH
) -> list[Selection]:
    """Pick the items to be rated from one run record, spread across the scenes.

    Round-robin by scene rather than in run order: the run is ordered by scene, so
    the first 20 come off the front of the list and stop before `delay_notice` and
    `workplace_keigo`. Those two are tier C — the strictest politeness floor — and
    the floor is the part of the scale two people are most likely to read
    differently (docs/ja/glossary.md §2). Agreement measured without tier C would
    not be measuring the contested part at all.

    Deterministic: same record, same 20 items, same order. The kit is printed and
    carried to a meeting, and a kit that cannot be regenerated cannot be checked
    against the ratings that come back.
    """
    if record.get("split") != "dev":
        raise ValueError(
            f"the kit is built from a dev run, not {record.get('split')!r} "
            "(docs/ja/glossary.md §7: test is read at the start and end of August only)"
        )

    dev_ids = {item.id for item in load_items(items_path) if item.split == "dev"}

    by_scene: dict[str, list[dict[str, Any]]] = {scene: [] for scene in SCENES}
    for result in record["results"]:
        # Checked before the eligibility filters, not after: the point is to catch a
        # record that mixes splits, and a mixed record could hide its test items
        # among the ones no rater would have seen anyway.
        if result["id"] not in dev_ids:
            raise ValueError(f"{result['id']} is in the run record but is not a dev item")
        if result["scene"] not in by_scene:
            raise ValueError(f"{result['id']}: unknown scene {result['scene']!r}")
        # Not just `predicted`: a correction that came back without a sentence or
        # without a reason has nothing for the §6 scale to grade.
        if not result.get("predicted"):
            continue
        if not result.get("corrected_sentence") or not result.get("reason_en"):
            continue
        by_scene[result["scene"]].append(result)

    for results in by_scene.values():
        results.sort(key=lambda result: result["id"])

    picked: list[dict[str, Any]] = []
    while len(picked) < size and any(by_scene.values()):
        for scene in SCENES:
            if len(picked) == size:
                break
            if by_scene[scene]:
                picked.append(by_scene[scene].pop(0))

    if len(picked) < size:
        raise ValueError(
            f"only {len(picked)} of the {size} items needed were corrected in this run; "
            "score more dev items before building the kit"
        )

    return [
        Selection(
            kit_no=number,
            id=result["id"],
            scene=result["scene"],
            learner_sentence=result["learner_sentence"],
            corrected_sentence=result["corrected_sentence"],
            reason_en=result["reason_en"],
        )
        for number, result in enumerate(picked, start=1)
    ]


def kit_record(record: dict[str, Any], selections: list[Selection]) -> dict[str, Any]:
    """The kit as JSON: what was shown, and which run it was taken from."""
    return {
        "kit_id": f"{record['run_id']}-rater-kit",
        "source_run": record["run_id"],
        "implementation": record["implementation"],
        "model": record["model"],
        "prompt_version": record["prompt_version"],
        "split": record["split"],
        # Carried because the reasons on the form appeal to it: the baseline was told
        # the learner is a beginner, and several of its explanations say so out loud.
        # A rater who does not know that reads those sentences as arbitrary.
        "level": record["level"],
        "n": len(selections),
        "scale": {
            key: {"label": label, "meaning": meaning} for key, (label, meaning) in SCALE.items()
        },
        "items": [selection.to_json() for selection in selections],
    }


def scoring_template(kit: dict[str, Any], rater: str) -> dict[str, Any]:
    """An empty form for one rater. Filled in by hand, one grade per item.

    Two of these exist per kit and they are filled at different times: the author's
    before 8/9 and the second rater's on the day. A form that carried the other
    rater's answers would make the agreement number meaningless, so nothing here
    ever holds both.

    Both are generated from the same `kit["items"]` rather than one being copied by
    hand from the other. The second rater's grades are transcribed off paper late on
    8/9, and a re-typed list of ids is where that transcription would go wrong
    invisibly — `agreement` can reject a bad grade, but it cannot recover an id that
    was never written down.
    """
    return {
        "kit_id": kit["kit_id"],
        "rater": rater,
        # In §6 order rather than alphabetical: this list is the only cue in the file
        # about what may be written in `rating`, and it sits next to a paper form
        # whose tick boxes are printed in that same order.
        "scale": list(SCALE),
        "ratings": [
            {"kit_no": item["kit_no"], "id": item["id"], "rating": None, "note": ""}
            for item in kit["items"]
        ],
    }


def agreement(first: dict[str, Any], second: dict[str, Any]) -> tuple[float, list[str]]:
    """`rater_agreement` and the ids the two raters graded differently.

    The disagreements are returned with the number because they are the part worth
    reading: §6 is fixed by rewriting the scale where two people read it
    differently, never by revising a rater's answers.

    Every way a form can be wrong is refused rather than absorbed. The second
    rater's grades are copied off paper by hand at the end of 8/9, and each of these
    would otherwise produce a number that looks like a result:

      - a missing or extra id, which would quietly change the denominator,
      - `"Valid"` instead of `"valid"`, read straight off the printed tick box,
        which would score every item as a disagreement,
      - `""` for an item that was skipped, which `is None` does not catch and which
        would then be counted as agreement — the exact failure this module is built
        to prevent.
    """
    if first["kit_id"] != second["kit_id"]:
        raise ValueError("the two forms are for different kits")

    grades = {rater["rater"]: _graded(rater) for rater in (first, second)}
    if len(grades) != 2:
        raise ValueError(f"both forms name the same rater ({first['rater']!r})")

    left, right = grades.values()
    if set(left) != set(right):
        difference = sorted(set(left) ^ set(right))
        raise ValueError(f"the two forms cover different items: {difference}")

    disagreed = sorted(item_id for item_id in left if left[item_id] != right[item_id])
    return (len(left) - len(disagreed)) / len(left), disagreed


def _graded(form: dict[str, Any]) -> dict[str, str]:
    """One form's grades by id, with anything unusable refused."""
    rater = form["rater"]
    grades: dict[str, str] = {}
    for row in form["ratings"]:
        item_id = row["id"]
        if item_id in grades:
            raise ValueError(f"{rater}: {item_id} appears twice")
        rating = row["rating"]
        if rating not in SCALE:
            raise ValueError(
                f"{rater}: {item_id} is graded {rating!r}, which is not one of {', '.join(SCALE)}"
            )
        grades[item_id] = rating
    if len(grades) != KIT_SIZE:
        raise ValueError(f"{rater}: {len(grades)} items graded, expected {KIT_SIZE}")
    return grades


def kit_markdown(kit: dict[str, Any]) -> str:
    """The printable form, in English.

    Printed rather than shown in the app: the venue's connection is not something
    to depend on, and the rater is judging corrections, not a demo. Deliberately
    plain — this gets printed, or read off a tablet, and written on with a pen.
    """
    ticks = "　　".join(f"☐ {label}" for label, _ in SCALE.values())
    lines = [
        f"# Japanese correction check — {kit['n']} items",
        "",
        "Thank you for helping. This takes about 30 minutes.",
        "",
        f"An AI was asked to correct sentences written by {LEVEL_WORDING[kit['level']]} learners "
        "of Japanese and to explain the mistake in English. Below is what it produced. It was "
        "told the learner's level and the situation, and the situation is printed above each "
        "item.",
        "**For each item, tick one box.** Judge the correction and the reason — not the "
        "learner. If the correction is fine but the explanation is weak, that is "
        "*Insufficient*, not *Valid*.",
        "",
        "| Tick | Means |",
        "|---|---|",
    ]
    for key in SCALE:
        label, meaning = SCALE[key]
        lines.append(f"| **{label}** | {meaning} |")
    lines += [
        "",
        SCALE_NOTE,
        "",
        "There is a space for a comment on each item. It is optional, but if you tick "
        "*Wrong*, one line about what is wrong is worth more than the tick.",
        "",
        "---",
        "",
    ]

    for item in kit["items"]:
        scene_label = SCENES[item["scene"]]
        # The exact situation string the model was given, not a paraphrase and not the
        # politeness tier. Two of the real items only make sense inside it — 「良い一日。」
        # is corrected to 「いってらっしゃい！」, which is right only because the neighbour is
        # leaving. A rater who has to guess the situation disagrees for that reason
        # rather than about the scale, and the disagreement then looks like a fault in
        # §6 that rewriting §6 cannot fix.
        situation, _ = scene_brief(item["scene"])
        _, requirement = politeness_floor(item["scene"])
        lines += [
            f"## {item['kit_no']}. {scene_label}",
            "",
            f"*The situation the AI was given: {situation}*",
            "",
            f"*How polite the learner has to be: {requirement}*",
            "",
            f"- **Learner wrote:** {item['learner_sentence']}",
            f"- **AI corrected it to:** {item['corrected_sentence']}",
            f"- **AI's reason:** {item['reason_en']}",
            "",
            ticks,
            "",
            "Comment: ______________________________________________",
            "",
        ]

    lines += [
        "---",
        "",
        f"Kit `{kit['kit_id']}` — {kit['n']} items, `{kit['split']}` split, "
        f"{kit['implementation']} ({kit['model']}).",
        "",
        "Name: ____________________　　Contact (WhatsApp): ____________________",
        "",
        "May I contact you again about this project?　☐ Yes　　☐ No",
    ]
    return "\n".join(lines) + "\n"


def whatsapp_message(kit: dict[str, Any], reply_by: str) -> str:
    """The same kit as one plain-text message, to be pasted into WhatsApp.

    The distribution route changed on 8/9. The plan was to hand over paper at the
    meeting and collect it there; a venue of rolling standing conversations had no
    half-hour in it, so the kit is sent to a phone instead and comes back whenever
    the rater gets to it. `kit_markdown` cannot do that job — WhatsApp renders no
    tables and no headings, so the printed form arrives as a wall of pipes.

    Two things this must get right, because both would show up as a number rather
    than as an error:

      - **The reply comes back as twenty numbered words, never as prose.** Free text
        has to be assigned to `valid`/`insufficient`/`wrong` by the person
        transcribing it, and `rater_agreement` would then partly measure how the
        author read the second rater — the one thing the metric is there to rule out.
        So the message ends with the twenty lines to copy, already numbered.
      - **The three words are printed in lower case**, matching
        `20260808-2041-rater-kit-second.json` exactly. The paper form prints them
        capitalised for the tick boxes, which made transcription a conversion step
        that `_graded` rejects (`"Valid"` is not a grade). Over chat there is no
        reason to keep that step: what comes back can be pasted straight in.

    The item text is reproduced verbatim, emphasis characters included. A reason is
    the object being graded, so rewriting one to render more tidily would change what
    the second rater is answering about.
    """
    missing = {"kit_id", "split", "level", "n", "items"} - set(kit)
    if missing:
        # Reached by passing a run record to --whatsapp, which is an easy slip: both
        # live under evals/ and both are JSON with the same ids in them. Worth a
        # sentence rather than a KeyError, like every other refusal in this module.
        raise ValueError(f"this is not a rater kit; it has no {', '.join(sorted(missing))}")
    if kit["split"] != "dev":
        raise ValueError(
            f"this kit is built from {kit['split']!r}; only a dev kit may leave the project "
            "(docs/ja/glossary.md §7: sending test items out would contaminate the "
            "published figures)"
        )

    grades = " / ".join(SCALE)
    rule = "─" * 24
    lines = [
        f"*Japanese correction check — {kit['n']} items*",
        "",
        "Thank you again for offering to look at these at Minna Shuugou. It takes about "
        f"30 minutes and there is no need to do it in one sitting. If you can send it "
        f"back by *{reply_by}* that would help me a lot.",
        "",
        f"An AI was asked to correct sentences written by {LEVEL_WORDING[kit['level']]} "
        "learners of Japanese and to explain the mistake in English. Below is what it "
        "produced. It was told the learner's level and the situation, and the situation "
        "is written above each item.",
        "",
        f"*For each item, answer with one of these words: {grades}.* Judge the correction "
        "and the reason — not the learner. If the correction is fine but the explanation "
        "is weak, that is _insufficient_, not _valid_.",
        "",
    ]
    for key, (_, meaning) in SCALE.items():
        lines += [f"*{key}* — {meaning}", ""]

    lines += [
        # The same convention as the printed form and docs/ja/glossary.md §6, differing
        # only in which case of the grade names it prints.
        scale_note("*insufficient*", "*wrong*", open="*", close="*"),
        "",
        "*How to reply:* copy the numbered list at the end of this message and write one "
        "of those words after each number. That is all I need. If you answer *wrong*, "
        "one line saying what is wrong is worth more to me than the word itself.",
        "",
        rule,
        "",
    ]

    for item in kit["items"]:
        situation, _ = scene_brief(item["scene"])
        _, requirement = politeness_floor(item["scene"])
        lines += [
            f"*{item['kit_no']}. {SCENES[item['scene']]}*",
            f"_Situation the AI was given: {situation}_",
            f"_How polite the learner has to be: {requirement}_",
            "",
            f"Learner wrote: {item['learner_sentence']}",
            f"AI corrected it to: {item['corrected_sentence']}",
            f"AI's reason: {item['reason_en']}",
            "",
            rule,
            "",
        ]

    lines += [
        f"*Copy from here and fill in the blanks — {grades}*",
        f"_({kit['kit_id']})_",
        "",
    ]
    lines += [f"{item['kit_no']}:" for item in kit["items"]]
    return "\n".join(lines) + "\n"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def refuse_if_graded(path: Path) -> None:
    """Stop before a rebuild erases a form somebody has already filled in.

    `--run` regenerates five files, and two of them are the blank forms. That is
    right the first time and destructive every time after: on 2026-08-09 it was run
    again to reprint the kit after a wording fix, and it overwrote the author's
    twenty grades with nulls. They existed nowhere else — a form is filled in by
    hand, over an hour, and the file had not been committed yet — and the recovery
    was luck.

    Refused rather than merged or backed up. The two forms are the whole of
    `rater_agreement`, and a command that reprints a form has no business touching
    the answers on it.

    Checked for every form before any file is written, so a refusal leaves the kit
    as it was rather than half rebuilt around the one file it would not touch.
    """
    if not path.exists():
        return
    existing = json.loads(path.read_text(encoding="utf-8"))
    graded = [row for row in existing.get("ratings", []) if row.get("rating")]
    if graded:
        raise SystemExit(
            f"{path} already has {len(graded)} grade(s) on it and would be erased. "
            "Move it aside if you really mean to start that form again."
        )


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, help="a baseline run record on dev; builds the kit")
    parser.add_argument(
        "--whatsapp",
        type=Path,
        metavar="KIT",
        help="a built kit; writes the same 20 items as a message to paste into WhatsApp",
    )
    # No default. The date belongs to a particular send, and a default here would go
    # stale silently — a message asking for a reply by a date already past reads as
    # boilerplate and gets treated as one.
    parser.add_argument(
        "--reply-by",
        help="the date to ask for the reply by, as it should be printed (with --whatsapp)",
    )
    parser.add_argument(
        "--score",
        type=Path,
        nargs=2,
        metavar=("FIRST", "SECOND"),
        help="two filled-in forms; prints rater_agreement and the disagreements",
    )
    parser.add_argument("--items", type=Path, default=ITEMS_PATH)
    parser.add_argument("--out", type=Path, default=RATER_DIR)
    # Both forms are generated here, so the two never disagree about which items the
    # kit contained. The second rater's grades are copied off paper late on 8/9, and
    # a hand-typed list of ids is the one part of that transcription no check can
    # repair afterwards.
    parser.add_argument(
        "--raters",
        nargs=2,
        default=["jun", "second"],
        help="the two names on the blank forms; the first is filled and sealed before 8/9",
    )
    args = parser.parse_args()

    if args.reply_by and not args.whatsapp:
        # Otherwise it falls through to --run and is silently dropped, which looks
        # like a message was written with that date on it.
        raise SystemExit("--reply-by only applies to --whatsapp")
    if args.score:
        _score(*args.score)
        return
    if args.whatsapp:
        _whatsapp(args.whatsapp, args.reply_by, args.out)
        return
    if not args.run:
        raise SystemExit(
            "give --run to build a kit, --whatsapp to write the message that sends it, "
            "or --score to compute rater_agreement"
        )

    record = json.loads(args.run.read_text(encoding="utf-8"))
    written, selections = build_kit(record, args.items, args.out, args.raters)

    # The scene list is the one thing worth reading in this output: `select` spreads
    # the 20 across the scenes so that tiers B and C are in the kit at all, and a kit
    # that quietly stopped before them would still print a plausible count.
    scenes = sorted({selection.scene for selection in selections})
    print(
        f"{len(selections)} items from {record['split']}, {len(scenes)} scenes: {', '.join(scenes)}"
    )
    for path in written:
        print(f"  -> {path}")


def build_kit(
    record: dict[str, Any], items_path: Path, out: Path, raters: list[str]
) -> tuple[list[Path], list[Selection]]:
    """Write the kit, the printed form and a blank form for each rater.

    Separated from `main` so the order of the two steps below can be tested. It is
    the whole of the command, and the part that matters is not what it writes but
    what it checks before writing anything.

    Returns what it wrote and what went into it, because the caller reports on both.
    """
    selections = select(record, KIT_SIZE, items_path)
    kit = kit_record(record, selections)

    # Every form first, before a single file is written. Rebuilding is a routine
    # thing to do — a wording fix, a reprint — and on 2026-08-09 doing it erased
    # twenty hand-written grades. A refusal has to leave the kit as it was rather
    # than half rebuilt around the one file it would not overwrite.
    forms = {out / f"{kit['kit_id']}-{rater}.json": rater for rater in raters}
    for path in forms:
        refuse_if_graded(path)

    written = [
        _write(out / f"{kit['kit_id']}.json", _dump(kit)),
        _write(out / f"{kit['kit_id']}.md", kit_markdown(kit)),
        *(_write(path, _dump(scoring_template(kit, rater))) for path, rater in forms.items()),
    ]
    return written, selections


def _whatsapp(kit_path: Path, reply_by: str | None, out: Path) -> None:
    """Write the sendable message for an already-built kit.

    Rendered from the kit JSON rather than rewritten by hand, for the same reason the
    two blank forms are generated together: the message, the printed form and the
    scoring templates all have to name the same twenty items, and the copy that gets
    sent is the one nobody can check afterwards.

    `.txt` rather than `.md`: it is meant to be pasted into a chat, and the extension
    is the only thing stopping it from being mistaken for the printable form.
    """
    if not reply_by:
        raise SystemExit("--whatsapp needs --reply-by (the date printed in the message)")

    kit = json.loads(kit_path.read_text(encoding="utf-8"))
    path = _write(out / f"{kit['kit_id']}-whatsapp.txt", whatsapp_message(kit, reply_by))
    print(f"{kit['n']} items from {kit['split']}, reply requested by {reply_by}")
    print(f"  -> {path}")


def _score(first: Path, second: Path) -> None:
    """Compute `rater_agreement` from two filled-in forms and show what split them.

    A command rather than a note to open a REPL: this is run once, at the end of a
    long day, and it is the last step of a measurement that cannot be repeated.
    """
    forms = [json.loads(path.read_text(encoding="utf-8")) for path in (first, second)]
    rate, disagreed = agreement(*forms)
    numbered = {row["id"]: row["kit_no"] for row in forms[0]["ratings"]}

    print(f"\nrater_agreement  {rate:.1%}  (n={len(forms[0]['ratings'])})")
    print(f"  raters         {forms[0]['rater']}, {forms[1]['rater']}")
    if not disagreed:
        print("\nNo disagreements.")
        return
    print(f"\n{len(disagreed)} disagreement(s) — read these, then fix §6, not the ratings:")
    grades = [{row["id"]: row["rating"] for row in form["ratings"]} for form in forms]
    for item_id in sorted(disagreed, key=lambda item_id: numbered[item_id]):
        print(f"  #{numbered[item_id]:<3} {item_id}  {grades[0][item_id]} / {grades[1][item_id]}")


if __name__ == "__main__":
    main()
