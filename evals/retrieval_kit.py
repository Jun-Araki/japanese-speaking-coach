"""Choosing the items `retrieval_hit_rate` is measured on, and the form to annotate.

THE ORDER IS THE POINT. The metric asks whether a sound piece of grounding came
back in the top three, and "sound" is a judgement. Made after seeing what retrieval
returned, it is worth nothing: eight beginner-grammar articles will each look
defensible next to almost any sentence, and the hit rate comes out near 100%
whatever the index does. So the reference article for each item is written down
FIRST, by hand, against the item alone — and only then is anything searched.

This script does the half that can be automated: pick the items, and print the form.

WHAT IS EXCLUDED. Twelve dev items appear verbatim somewhere in the reference
(tests/test_grammar_reference.py lists them with reasons — set phrases, mostly,
which cannot be explained without being written down). Retrieval finds those by
string overlap, and counting them would measure the overlap rather than the
grammar. They are dropped before selection rather than annotated and excluded
afterwards, so the sample is never chosen from a pool that includes them.

WHY `false` ITEMS ARE IN IT. Ten of the thirty are sentences that need no
correction. Check 3 suppresses a correction when nothing could be retrieved to
ground it, so "can the index find support for LEAVING THIS ALONE" is the question
that check depends on — and a sample of only `true` items never asks it.

TEN AND TWENTY. The first ten set `score_min`; the remaining twenty measure the hit
rate. Deciding a threshold and reporting a score on the same items is the same
mistake as tuning on the test split, in miniature.

Run:  .venv/bin/python -m evals.retrieval_kit
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from evals.dataset import ITEMS_PATH, Item, load_items

KIT_DIR: Final = Path("evals/retrieval")
GRAMMAR_DIR: Final = Path("data/grammar")
ACCEPTED_OVERLAP_PATH: Final = GRAMMAR_DIR / "accepted_overlap.json"

NEEDS_CORRECTION_SAMPLE: Final = 20
ALREADY_NATURAL_SAMPLE: Final = 10
THRESHOLD_SAMPLE: Final = 10


def accepted_overlap() -> frozenset[str]:
    """Ids whose text is in the reference on purpose (data/grammar/accepted_overlap.json)."""
    loaded = json.loads(ACCEPTED_OVERLAP_PATH.read_text(encoding="utf-8"))
    return frozenset(loaded["items"])


def articles() -> dict[str, str]:
    """Article id to title, read from the files rather than listed here.

    A hand-kept list would drift the moment a ninth article is written, and the
    form would then offer a choice that does not exist.
    """
    found = {}
    for path in sorted(GRAMMAR_DIR.glob("*.md")):
        title = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("title:"):
                title = line.removeprefix("title:").strip().strip('"')
                break
        found[path.stem.split("-", 2)[0] + "-" + path.stem.split("-")[1]] = title
    return found


def select(items: list[Item]) -> list[Item]:
    """Pick the sample, spread across scenes, in a way that reruns identically.

    Round-robin by scene rather than the first N: the run records are in scene
    order, and taking the front of the list exhausts `greeting` and never reaches
    `workplace_keigo` — the two tiers where grounding is hardest to find. Week 1
    made exactly this mistake choosing the rater kit.
    """
    pool = [
        item
        for item in items
        if item.split == "dev" and item.id not in accepted_overlap()
    ]
    chosen: list[Item] = []
    for label, wanted in ((True, NEEDS_CORRECTION_SAMPLE), (False, ALREADY_NATURAL_SAMPLE)):
        by_scene: dict[str, list[Item]] = {}
        for item in pool:
            if item.needs_correction is label:
                by_scene.setdefault(item.scene, []).append(item)
        taken: list[Item] = []
        while len(taken) < wanted:
            progressed = False
            for scene in sorted(by_scene):
                if by_scene[scene] and len(taken) < wanted:
                    taken.append(by_scene[scene].pop(0))
                    progressed = True
            if not progressed:
                break
        chosen.extend(taken)
    return chosen


def worksheet(chosen: list[Item], titles: dict[str, str]) -> str:
    """The form. One item per block, with the article ids to choose from.

    The label and the reference answer are shown: these are `dev` items and the
    person filling this in wrote them. What must NOT appear is anything retrieval
    returned, and nothing here has been searched yet — that is the whole sequence.
    """
    lines = [
        "# Which article should ground each item",
        "",
        "Fill in `grounds:` for every item **before running any search**. More than one id is",
        "fine — one topic is meant to be covered by more than one article. Write `none` if no",
        "article covers it; that is a finding about the reference, not a blank.",
        "",
        "The first block sets the retrieval threshold. The second is what the published hit",
        "rate is measured on. Do not look at search results while filling either in.",
        "",
        "## Articles",
        "",
    ]
    lines += [f"- `{key}` — {title}" for key, title in titles.items()]

    for start, size, heading in (
        (0, THRESHOLD_SAMPLE, "Threshold-setting sample (not published)"),
        (THRESHOLD_SAMPLE, len(chosen), "Measurement sample (the published hit rate)"),
    ):
        lines += ["", f"## {heading}", ""]
        for index, item in enumerate(chosen[start:size], start=start + 1):
            label = "needs correction" if item.needs_correction else "already natural"
            lines += [
                f"### {index}. {item.id} · {item.scene} · {label}",
                "",
                f"- learner: {item.learner_sentence}",
            ]
            if item.corrected_sentence:
                lines.append(f"- corrected: {item.corrected_sentence}")
            lines += ["- grounds: ", ""]
    return "\n".join(lines) + "\n"


def main() -> None:
    items = load_items(ITEMS_PATH)
    chosen = select(items)
    titles = articles()

    KIT_DIR.mkdir(parents=True, exist_ok=True)
    (KIT_DIR / "selection.json").write_text(
        json.dumps(
            {
                "excluded_for_verbatim_overlap": sorted(accepted_overlap()),
                "threshold_sample": [item.id for item in chosen[:THRESHOLD_SAMPLE]],
                "measurement_sample": [item.id for item in chosen[THRESHOLD_SAMPLE:]],
                "articles": titles,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (KIT_DIR / "worksheet.md").write_text(worksheet(chosen, titles), encoding="utf-8")

    natural = sum(1 for item in chosen if not item.needs_correction)
    print(f"{len(chosen)} items: {len(chosen) - natural} needing correction, {natural} natural")
    print(f"  excluded for appearing verbatim in the reference: {len(accepted_overlap())}")
    measured = len(chosen) - THRESHOLD_SAMPLE
    print(f"  threshold sample {THRESHOLD_SAMPLE}, measurement sample {measured}")
    print(f"  -> {KIT_DIR / 'worksheet.md'}")


if __name__ == "__main__":
    main()
