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

WHAT THE EXCLUSION MISSES, MEASURED. `accepted_overlap` drops items whose WHOLE
sentence sits in the reference. It does not drop an item whose distinctive phrase
does — 「見てもいいですか？」 shares seven of its eight characters with the article that
teaches 〜てもいいですか, and would be found by an index that understood nothing. So
`lexical_share` is computed for every sampled item and printed on the form, BEFORE
anything is searched and before the grounds are written. It is not used to redraw
the sample: dropping items after seeing their overlap would be choosing the sample
to suit the number. It is pre-registered as a covariate, so the hit rate can be
reported both over all twenty and over the low-overlap ones alone.

Run:  .venv/bin/python -m evals.retrieval_kit
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

from evals.dataset import ITEMS_PATH, Item, load_items

KIT_DIR: Final = Path("evals/retrieval")
WORKSHEET_PATH: Final = KIT_DIR / "worksheet.md"
GRAMMAR_DIR: Final = Path("data/grammar")
ACCEPTED_OVERLAP_PATH: Final = GRAMMAR_DIR / "accepted_overlap.json"

NEEDS_CORRECTION_SAMPLE: Final = 20
ALREADY_NATURAL_SAMPLE: Final = 10
THRESHOLD_SAMPLE: Final = 10

# NO THRESHOLD ON THE OVERLAP, DELIBERATELY. An earlier draft of this file defined
# HIGH_OVERLAP = 0.60 and promised a hit rate "over the low-overlap items alone".
# The audit of 8/13 took it apart: the constant was never read by anything, no `>`
# against `>=` was ever written down, one item sits exactly on 0.60, and the number
# had been carried over from a different measure (3-gram Jaccard) in design.md
# rather than derived here. A subgroup boundary nobody can check is worse than no
# subgroup at all, so the share is disclosed per item and no bucket is defined.
#
# Dropped before comparing: punctuation, markdown emphasis and 〜. Emphasis, because
# an article writes the rule-bearing part in bold — 「どこ**に**住んでいますか」; 〜,
# because the headings that state a pattern write it as 〜てくれてありがとう, and
# keeping the tilde truncates the match at exactly the phrases the articles are
# about. Neither changes what the contamination check catches (measured: the same
# twelve dev items, before and after); both change the overlap this file reports.
_PUNCTUATION: Final = re.compile(r"[。、？！「」*_`〜～\s]")

# Articles are joined by a character normalise never produces, so no match can run
# off the end of one article and into the next. Without it the corpus is a single
# blob and a span can be assembled from two documents that never sat together.
_ARTICLE_BREAK: Final = "\x00"


def accepted_overlap() -> frozenset[str]:
    """Ids whose text is in the reference on purpose (data/grammar/accepted_overlap.json)."""
    loaded = json.loads(ACCEPTED_OVERLAP_PATH.read_text(encoding="utf-8"))
    return frozenset(loaded["items"])


def normalise(text: str) -> str:
    """Strip the punctuation that makes two identical phrases compare unequal."""
    return _PUNCTUATION.sub("", text)


def article_texts() -> dict[str, str]:
    """Each article's text, normalised, keyed by article id."""
    return {
        _article_id(path): normalise(path.read_text(encoding="utf-8"))
        for path in sorted(GRAMMAR_DIR.glob("*.md"))
    }


def reference_text() -> str:
    return _ARTICLE_BREAK.join(article_texts().values())


def lexical_share(sentence: str, corpus: str) -> float:
    """What fraction of the sentence is its longest run of characters found verbatim.

    A crude measure on purpose. It is not trying to predict what an embedding will
    do; it is answering the one question a reader of the hit rate will ask — could
    this item have been found by matching characters alone — and a longest common
    substring answers that without a model.

    Read the share with `lexical_source` beside it and not on its own. Two limits
    the 8/13 audit measured, neither of which the number shows: it is quantised at
    1/len, so a four-character sentence can only score 0.25, 0.50, 0.75 or 1.00 and
    its 0.25 may be one 「い」 that appears in all eight articles; and it says nothing
    about WHICH article the run was found in, which is the whole question — an item
    can share nine characters with an article that is not its grounding, and that
    overlap pulls retrieval away from the right answer rather than towards it.
    """
    text = normalise(sentence)
    if not text:
        return 0.0
    longest = 0
    for start in range(len(text)):
        for end in range(len(text), start + longest, -1):
            if text[start:end] in corpus:
                longest = end - start
                break
    return longest / len(text)


def lexical_source(sentence: str) -> str:
    """Which article holds the longest verbatim run, ties broken by id order.

    Without this the share is unsigned. `eval-031` shares 「ってくれてありがとう」 with
    grammar-007 while its grounding is grammar-002: a high share that makes the item
    HARDER, and reporting it as "could have been found by matching characters" says
    the opposite of what is true.
    """
    best_share, best_id = 0.0, "none"
    for article_id, text in article_texts().items():
        share = lexical_share(sentence, text)
        if share > best_share:
            best_share, best_id = share, article_id
    return best_id


def _article_id(path: Path) -> str:
    parts = path.stem.split("-")
    return f"{parts[0]}-{parts[1]}"


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
        found[_article_id(path)] = title
    return found


def select(items: list[Item]) -> list[Item]:
    """Pick the sample, spread across scenes, in a way that reruns identically.

    Round-robin by scene rather than the first N: the run records are in scene
    order, and taking the front of the list exhausts `greeting` and never reaches
    `workplace_keigo` — the two tiers where grounding is hardest to find. Week 1
    made exactly this mistake choosing the rater kit.
    """
    pool = [item for item in items if item.split == "dev" and item.id not in accepted_overlap()]
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
        "## The rule being applied",
        "",
        "List an article when it **states the rule** — the one broken, for an item needing",
        "correction, or the one that licenses the sentence, for an item that is already",
        "natural. Do not list an article that merely mentions a word in the sentence: every",
        "id added makes a hit easier to score, so a generous sheet reports a good index",
        "whatever the index does.",
        "",
        "`lexical_share` is how much of the sentence appears verbatim in one article, and",
        "which article that is. It is not a hint and must not be read as one. Read the two",
        "together: a high share **in the article you are about to write down** means the",
        "item could have been found by matching characters, so its hit says less; a high",
        "share in a different article means the opposite, because that overlap pulls",
        "retrieval away from the right answer. No threshold is drawn on it — the shares are",
        "disclosed per item and no subgroup rate is computed from them.",
        "",
        "## Articles",
        "",
    ]
    lines += [f"- `{key}` — {title}" for key, title in titles.items()]

    corpus = reference_text()
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
            share = lexical_share(item.learner_sentence, corpus)
            source = lexical_source(item.learner_sentence)
            lines += [f"- lexical_share: {share:.2f} ({source})", "- grounds: ", ""]
    return "\n".join(lines) + "\n"


class WorksheetError(ValueError):
    """The filled-in worksheet cannot be read as annotations."""


# Matched with the indentation stripped. A markdown formatter indents list items
# under a heading, and the 8/13 audit demonstrated the consequence end to end: the
# two-space version stopped matching, `is_filled` went False, and the next run of
# this script regenerated the sheet and destroyed thirty annotations that exist
# nowhere else. Reading a slightly reformatted file is not a favour to the writer,
# it is the difference between losing the work and not.
_HEADING: Final = "### "
_GROUNDS: Final = "- grounds:"


def load_grounds(path: Path = WORKSHEET_PATH) -> dict[str, tuple[str, ...]]:
    """Read the filled form back, or refuse to.

    Every failure here is loud, and that includes the structural ones. A blank read
    as "no article covers it" would turn an unfinished sheet into a finding about
    the reference; an answer with no heading above it, or a second heading for an id
    already seen, would be dropped or silently overwritten. All of them reach the
    published number wearing the clothes of a judgement, so none of them is allowed
    to pass quietly.
    """
    known = set(articles())
    found: dict[str, tuple[str, ...]] = {}
    item_id: str | None = None
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if line.startswith(_HEADING):
            parts = line.split()
            # "### Review notes" is a heading a reader may reasonably add. It is not
            # an item, and it must not take an IndexError down with it.
            if len(parts) < 3 or not parts[2].startswith("eval-"):
                continue
            if item_id is not None:
                raise WorksheetError(f"line {number}: {item_id} has no grounds written")
            item_id = parts[2]
            if item_id in found:
                raise WorksheetError(f"line {number}: {item_id} appears twice")
        elif line.startswith(_GROUNDS):
            if item_id is None:
                raise WorksheetError(f"line {number}: grounds with no item above it")
            written = line.removeprefix(_GROUNDS).strip()
            if not written:
                raise WorksheetError(f"{item_id} has no grounds written")
            if written == "none":
                found[item_id] = ()
            else:
                ids = tuple(part.strip() for part in written.split(","))
                unknown = [one for one in ids if one not in known]
                if unknown:
                    raise WorksheetError(f"{item_id} names no such article: {unknown}")
                found[item_id] = ids
            item_id = None
    if item_id is not None:
        raise WorksheetError(f"{item_id} has no grounds written")
    return found


def is_filled(path: Path = WORKSHEET_PATH) -> bool:
    """Whether anyone has started answering, so a rerun does not wipe the answers."""
    if not path.exists():
        return False
    return any(
        line.strip().startswith(_GROUNDS) and line.strip().removeprefix(_GROUNDS).strip()
        for line in path.read_text(encoding="utf-8").splitlines()
    )


def main() -> None:
    items = load_items(ITEMS_PATH)
    chosen = select(items)
    titles = articles()

    # selection.json is derived, so it is rewritten every time. The earlier version
    # raised before both writes, which meant that once the sheet was annotated the
    # record of WHICH items were sampled could never be refreshed — it went stale
    # in silence while the worksheet tests went red, and the only way to fix it was
    # to move the worksheet aside, the one thing the guard exists to prevent.
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

    if is_filled():
        # The annotations are the expensive half and they cannot be reconstructed:
        # they are judgements made before anything was searched, and a sheet
        # regenerated after retrieval exists can never be that again.
        raise SystemExit(
            f"{WORKSHEET_PATH} already has answers in it, so it was left alone "
            f"({KIT_DIR / 'selection.json'} was refreshed). Move the sheet aside first if "
            "you really mean to draw the sample again — the grounds cannot be re-made "
            "once search results have been seen."
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
