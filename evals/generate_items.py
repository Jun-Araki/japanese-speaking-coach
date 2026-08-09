"""Candidate generation for the evaluation dataset.

The method, and the reason it is worth having as a script rather than a chat
session: candidates are generated automatically, and every one of them is then
verified by a native speaker before it becomes an item. That is what makes the
dataset able to grow past 120 without the cost growing the same way, and it is
the part of this project that is actually about evaluation methodology.

WHAT THIS SCRIPT DOES NOT DO: it does not label anything. It writes a candidate
file with an `intended_label` — what the sentence was *asked* to be — and the
native verdict is applied afterwards. The distinction matters more than it looks:

  - If the model both writes the sentence and decides its label, then the
    `false` items are exactly the sentences this model already believes are
    natural. The correction engine is the same model. `over_correction_rate`
    would then be measured on the cases most flattering to it.
  - So the prompt asks for natural sentences that are plain, blunt or casual —
    the ones a strict teacher is tempted to "improve" — and the disagreements
    between `intended_label` and the native verdict are kept. How often the
    generator was wrong is itself a number worth reporting.

WHAT CHANGED IN v2 (day 5): v1 was written before the labelling criteria existed.
Verifying its day-5 batch overturned 14 of 60 candidates, and 12 of those 14 came
from two rules the prompt had never been told about — the politeness floor per
scene and the rule that 「あなた」 alone is not a defect (docs/ja/glossary.md §2,
both fixed on day 3). The generator was being asked to hit a target it could not
see. v2 states the criteria; the labelling authority does not move, because the
model still never assigns a label.

This does not touch how anything is measured. The correction prompt is unchanged,
and a candidate is still only a proposal until a native speaker rules on it.

Run:  .venv/bin/python -m evals.generate_items --batch 1
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Final

from langchain_core.messages import HumanMessage, SystemMessage

from dialogue.scenes import SCENES, politeness_floor, scene_brief
from evals.dataset import ITEMS_PATH, load_items
from llm import active_model_name, as_text, build_chat_model

PROMPT_VERSION: Final = "generate-items-v2"

CANDIDATES_DIR: Final = Path("data/evaluation/candidates")

# Unlike the correction call, this one wants variety: at temperature 0 the model
# returns the same handful of textbook mistakes for every scene.
TEMPERATURE: Final = 1.0

# Per scene: how many candidates to ask for that should need correction, and how
# many that should be fine as they are. Batch 1 (day 3) and batch 2 (day 5) each
# use this plan, which lands the finished dataset on 90 needs-correction and 30
# natural, and on 24/24/18/18/18/18 across the scenes.
#
# The easy scenes get more items because that is where beginners actually spend
# their time; the later scenes exist to show the ceiling, not to be sampled
# evenly. Every per-scene total is divisible by 3 so the 2:1 split comes out
# exactly right per scene rather than only in aggregate.
BATCH_PLAN: Final[dict[str, tuple[int, int]]] = {
    "greeting": (9, 3),
    "self_introduction": (9, 3),
    "thanks": (7, 2),
    "simple_request": (7, 2),
    "delay_notice": (7, 2),
    "workplace_keigo": (6, 3),
}

SYSTEM_PROMPT: Final = """\
You write practice material for a tool that helps beginners of Japanese in \
Bangalore. Your output is reviewed by a native speaker before it is used, so \
write what you actually believe, not what is safest.

You produce Japanese sentences that a LEARNER might say — not model answers. \
They are short, because beginners speak in short sentences. Many learners here \
come to Japanese through anime and through English, so their mistakes tend to be \
the ones that come from those two places.

Answer with a JSON array and nothing else — no markdown fence, no commentary:

[{{"learner_sentence": "...", "intended_label": "needs_correction" or "natural",
   "corrected_sentence": "..." or null, "reason_en": "..." or null,
   "note_en": "one short sentence on what makes this item worth having"}}]

- `corrected_sentence` and `reason_en` are filled in only for \
"needs_correction" items, and are null for "natural" ones.
- `corrected_sentence` repairs the learner's sentence with the smallest change \
that works. Do not write a better sentence of your own.
- `reason_en` is one or two sentences of English. Quote Japanese inside 「」 when \
you need to point at a word.
"""

USER_PROMPT: Final = """\
Situation: {situation}

How polite this listener has to be spoken to (tier {tier}): {floor}

Write {needs_count} sentences labelled "needs_correction" and {natural_count} \
sentences labelled "natural", for this situation.

The "needs_correction" ones are wrong in one of these ways, and you should spread \
them across the four:
- a wrong particle, a wrong conjugation, or a missing required element
- the sentence is below the politeness floor stated above
- grammatical, but no Japanese speaker would say it — usually a word-for-word \
translation from English
- a fixed expression that has been altered

Each of them should be wrong in ONE way only. A sentence with three problems in \
it cannot be a clean test of anything.

Three rules decide whether a "needs_correction" sentence is usable at all:

1. IT IS WRONG AS WRITTEN. Not wrong under a guess about what the learner meant. \
A sentence that is fine Japanese but says something other than what you imagine \
they intended is a natural sentence, and it will be relabelled.
2. ABOVE THE FLOOR, POLITENESS IS NEVER THE PROBLEM. In a tier A situation, \
casual speech is correct — such a sentence may only be wrong for grammar, for \
being something no Japanese speaker says, or for altering a fixed expression. \
Being *more* polite than the floor is never wrong either.
3. 「あなた」 IS NOT A DEFECT. Do not write a sentence whose only problem is that \
it uses 「あなた」. If it also reads as translated English, say that instead — the \
word order or the translation is the reason, and 「あなた」 is not.

The "natural" ones are the harder half, and they decide whether this dataset can \
measure anything at all. They must be sentences a Japanese speaker would accept \
without stopping, AND sentences that a strict teacher would be tempted to \
"improve". Plain, blunt, short, or casual-but-real. Do not write polished model \
answers: a dataset of textbook-perfect sentences cannot detect a system that \
corrects things it should have left alone. **They must still clear the politeness \
floor above** — below it, the sentence is a "needs_correction" one.

Vary the length, and vary how confident the learner sounds.
{focus_clause}{avoid_clause}"""

# Counting the finished dataset shows which mistakes it cannot see. Day 5 found
# ten items turning on に versus で and none at all on counters, transitive pairs,
# giving and receiving, or the direction of keigo — so `detection_accuracy` would
# have been partly a measure of one particle. Asking for a replacement in the same
# shape as the item it replaces is how that gets fixed without growing the set.
_FOCUS_CLAUSE: Final = """
This batch is replacing items the dataset already has too many of. Aim the \
"needs_correction" sentences at this, and do not fall back on the mistakes you \
would normally reach for: {focus}
"""

_AVOID_CLAUSE: Final = """
These sentences already exist. Do not write them again, and do not write a \
near-duplicate of one. It counts as a near-duplicate if it keeps the same \
sentence frame with a different word in it, OR if it tests the same mistake in \
the same construction — 「私はオフィスでいます」 and 「会社でいます」 are one item, \
not two, and so are 「ありがとうを言います」 and 「感謝を言います」:
{sentences}
"""

_JSON_ARRAY: Final = re.compile(r"\[.*\]", re.DOTALL)


class CandidateFormatError(ValueError):
    """The model's answer was not the JSON array the prompt asked for."""


def generate_batch(
    batch: int, plan: dict[str, tuple[int, int]] | None = None, focus: str | None = None
) -> dict[str, Any]:
    """Generate one batch of candidates for every scene in the plan."""
    plan = plan or BATCH_PLAN
    avoid = _existing_sentences()
    candidates: list[dict[str, Any]] = []

    for scene, (needs_count, natural_count) in plan.items():
        scene_candidates = generate_for_scene(scene, needs_count, natural_count, avoid, focus)
        candidates += scene_candidates
        # Later scenes are told about the sentences the earlier ones produced, so
        # the same "おはようです" does not arrive six times in one run.
        avoid += [entry["learner_sentence"] for entry in scene_candidates]

    return {
        "batch": batch,
        "generated_on": date.today().isoformat(),
        "model": active_model_name(),
        "prompt_version": PROMPT_VERSION,
        "focus": focus,
        "verified": False,
        "candidates": candidates,
    }


def generate_for_scene(
    scene: str,
    needs_count: int,
    natural_count: int,
    avoid: list[str],
    focus: str | None = None,
) -> list[dict[str, Any]]:
    """Ask for one scene's candidates and return them tagged with the scene."""
    situation, _ = scene_brief(scene)
    tier, floor = politeness_floor(scene)
    model = build_chat_model(temperature=TEMPERATURE)
    answer = as_text(
        model.invoke(
            [
                SystemMessage(SYSTEM_PROMPT),
                HumanMessage(
                    USER_PROMPT.format(
                        situation=situation,
                        tier=tier,
                        floor=floor,
                        needs_count=needs_count,
                        natural_count=natural_count,
                        focus_clause=_focus_clause(focus),
                        avoid_clause=_avoid_clause(avoid),
                    )
                ),
            ]
        ).content
    )
    return [{"scene": scene, **entry} for entry in parse_candidates(answer)]


def parse_candidates(answer: str) -> list[dict[str, Any]]:
    """Turn one model answer into candidate rows, or say why it cannot be one.

    Parsed by hand for the same reason the correction engine is: constrained
    decoding would hide how often the format actually holds, and here it would
    also mean two different code paths for reading model output in one project.
    """
    match = _JSON_ARRAY.search(answer)
    if match is None:
        raise CandidateFormatError("there was no JSON array in the answer")
    try:
        payload = json.loads(match.group())
    except json.JSONDecodeError as exc:
        raise CandidateFormatError(f"the JSON did not parse ({exc.msg})") from exc
    if not isinstance(payload, list):
        raise CandidateFormatError("the JSON was not an array")

    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(payload):
        if not isinstance(entry, dict):
            raise CandidateFormatError(f"candidate {index} was not an object")
        sentence = entry.get("learner_sentence")
        label = entry.get("intended_label")
        if not isinstance(sentence, str) or not sentence.strip():
            raise CandidateFormatError(f"candidate {index} had no learner_sentence")
        if label not in ("needs_correction", "natural"):
            raise CandidateFormatError(f"candidate {index} had intended_label {label!r}")
        rows.append(
            {
                "learner_sentence": sentence.strip(),
                "intended_label": label,
                "corrected_sentence": _text_or_none(entry.get("corrected_sentence")),
                "reason_en": _text_or_none(entry.get("reason_en")),
                "note_en": _text_or_none(entry.get("note_en")),
            }
        )
    return rows


def _focus_clause(focus: str | None) -> str:
    if not focus:
        return ""
    return _FOCUS_CLAUSE.format(focus=focus)


def _avoid_clause(avoid: list[str]) -> str:
    if not avoid:
        return ""
    return _AVOID_CLAUSE.format(sentences="\n".join(f"- {sentence}" for sentence in avoid))


def _existing_sentences() -> list[str]:
    """Sentences already in the dataset or in an earlier candidate file.

    Day 5 generates the second batch against a dataset that already exists, and
    duplicates there are expensive: they are only caught during verification, by
    which point the model has been paid for them and the batch is short.
    """
    sentences: list[str] = []
    if ITEMS_PATH.exists():
        sentences += [item.learner_sentence for item in load_items()]
    if CANDIDATES_DIR.exists():
        for path in sorted(CANDIDATES_DIR.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            sentences += [
                str(entry["learner_sentence"])
                for entry in payload.get("candidates", [])
                if "learner_sentence" in entry
            ]
    return sentences


def _text_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, required=True, help="1 for day 3, 2 for day 5")
    parser.add_argument(
        "--scene",
        choices=sorted(SCENES),
        help="generate one scene only, for when a scene has to be redone",
    )
    parser.add_argument(
        "--needs",
        type=int,
        help="override how many needs_correction candidates to ask for (with --scene)",
    )
    parser.add_argument(
        "--natural",
        type=int,
        help="override how many natural candidates to ask for (with --scene)",
    )
    parser.add_argument(
        "--focus",
        help="what kind of mistake this batch should aim at, for replacing over-represented items",
    )
    args = parser.parse_args()

    plan = None
    if args.scene:
        needs, natural = BATCH_PLAN[args.scene]
        plan = {
            args.scene: (
                args.needs if args.needs is not None else needs,
                args.natural if args.natural is not None else natural,
            )
        }
    result = generate_batch(args.batch, plan, args.focus)

    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"-{args.scene}" if args.scene else ""
    if args.focus:
        suffix += "-focus"
    # The prompt version is in the filename, not only inside the file: day 5
    # regenerated a batch after changing the prompt, and a run that silently
    # overwrites the candidates it is being compared against cannot report the
    # comparison. Different prompt, different file.
    path = (
        CANDIDATES_DIR / f"batch{args.batch}{suffix}-{PROMPT_VERSION}-{result['generated_on']}.json"
    )
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(result['candidates'])} candidates -> {path}")


if __name__ == "__main__":
    main()
