"""Measuring how often the AI's reply stays inside the learner's vocabulary level.

TWO NUMBERS, NOT ONE. The validation node regenerates a reply that fails this same
check, using this same function — so once it is wired in, "share of replies that
pass" converges on "share that pass twice in a row" and climbs toward 100%
regardless of how hard the replies actually are. Reporting only that would be the
`format_compliance_rate` trap again: a metric that is satisfied by the machinery
built to satisfy it (correction/engine.py, on why structured decoding is not used).

So the headline is the FIRST-SHOT rate — the quality of the replies before any
gate — and the post-regeneration rate is reported beside it as the operational
figure. docs/ja/glossary.md §5 carries which target attaches to which.

Both figures come out of one pass. `checked_reply` hands back the discarded first
attempt along with the final text, so the ungated reply is judged as well as the
one the learner would see, and neither number depends on running the script twice
under different conditions.

That is not how this started. The first version called `reply()`, and when the gate
landed inside `reply()` a commit later, this file went on calling it — the
"first-shot" figure would have become the post-regeneration figure, silently, and
the only sign would have been the number improving. The metric designed around
that exact trap walked into it from the other side.

Run:  .venv/bin/python -m evals.level_compliance
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from dialogue import Utterance, opening_line
from dialogue.reply import MAX_REGENERATIONS, PROMPT_VERSION, TEMPERATURE, checked_reply
from dialogue.scenes import LEVELS, SCENES
from evals.score import RUNS_DIR
from evals.script import SCRIPT, TURNS
from llm import active_model_name
from nlp import level_check

# The tier tables and the mapping from level to tier are as much a part of this
# number as the prompt is. A run measured before the mapping was calibrated is not
# comparable with one measured after, and only this file knows to say so.
TIER_VERSION: Final = "bccwj-suw+luw-cuts70-80-90-95"


def script_digest() -> str:
    """Fingerprint of the fixed script.

    The learner's side is what is being held still, so a run measured against a
    different script is a different measurement — and neither `prompt_version` nor
    `tier_version` moves when a line changes. Two lines were replaced on 8/12 when
    they turned out to collide with the held-out split, and without this the old
    and new runs are indistinguishable by provenance while carrying the same key
    names. Same reasoning as `items_digest` on the correction side.
    """
    canonical = json.dumps(SCRIPT, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:12]


@dataclass(frozen=True)
class ReplyOutcome:
    """One reply, judged before and after the gate.

    `first_shot_passes` is the reply as the model produced it; `passes` is the one
    the learner would have seen. On a reply that was not regenerated they are the
    same value about the same text, which is correct and is why they are stored
    separately rather than derived from `attempts`.
    """

    scene: str
    level: str
    turn: int
    text: str
    first_shot: str
    attempts: int
    judged: int
    over_level: tuple[str, ...]
    first_shot_over_level: tuple[str, ...]
    first_shot_unknown: tuple[str, ...]
    far_over_level: tuple[str, ...]
    unknown: tuple[str, ...]
    passes: bool
    first_shot_passes: bool


def measure(levels: tuple[str, ...] = tuple(LEVELS)) -> list[ReplyOutcome]:
    """Run the fixed script through every scene and level, judging each reply.

    History is rebuilt per level rather than shared: the partner's replies differ
    by level, and a beginner conversation seeded with an intermediate reply is not
    the conversation this measures.
    """
    outcomes: list[ReplyOutcome] = []
    for level in levels:
        for scene in SCENES:
            history = [Utterance("partner", opening_line(scene))]
            for turn, learner in enumerate(SCRIPT[scene][:TURNS], start=1):
                history.append(Utterance("learner", learner))
                answer = checked_reply(scene, level, history)
                history.append(Utterance("partner", answer.text))
                check = level_check(answer.text, level)
                first_check = level_check(answer.first_shot, level)
                outcomes.append(
                    ReplyOutcome(
                        scene=scene,
                        level=level,
                        turn=turn,
                        text=answer.text,
                        first_shot=answer.first_shot,
                        attempts=answer.attempts,
                        judged=check.judged,
                        over_level=tuple(word.surface for word in check.over_level),
                        first_shot_over_level=tuple(
                            word.surface for word in first_check.over_level
                        ),
                        first_shot_unknown=tuple(word.surface for word in first_check.unknown),
                        far_over_level=tuple(word.surface for word in check.far_over_level),
                        unknown=tuple(word.surface for word in check.unknown),
                        passes=check.passes,
                        # Judged, not inferred from `attempts`. Deriving it from
                        # whether the gate fired ties the headline figure to
                        # `max_regenerations`: set that to zero and every reply
                        # reports as passing first time, from a value in a config
                        # file. The check costs nothing — the text is already here.
                        first_shot_passes=first_check.passes,
                    )
                )
    return outcomes


def run_record(outcomes: list[ReplyOutcome], run_id: str) -> dict[str, Any]:
    """The JSON for one measurement, in the shape the scorer's records use.

    `regenerated` is stated rather than implied. Once the validation node is in,
    a record without it could not be told apart from one taken before, and the two
    numbers mean different things.
    """
    by_level = {
        level: [outcome for outcome in outcomes if outcome.level == level] for level in LEVELS
    }
    words = sum(outcome.judged for outcome in outcomes)
    return {
        "run_id": run_id,
        "measurement": "level_compliance",
        "model": active_model_name(),
        "prompt_version": PROMPT_VERSION,
        "temperature": TEMPERATURE,
        "tier_version": TIER_VERSION,
        "script_digest": script_digest(),
        "regenerated": True,
        "max_regenerations": MAX_REGENERATIONS,
        "trials": 1,
        "n": len(outcomes),
        "date": run_id[:8],
        "first_shot_rate": _rate([outcome.first_shot_passes for outcome in outcomes]),
        "first_shot_rate_by_level": {
            level: _rate([outcome.first_shot_passes for outcome in group])
            for level, group in by_level.items()
        },
        # The operational figure, and the one the 90% target attaches to. Published
        # next to the first-shot rate with the note that it is the result of gating
        # with the same function and so is not independent evidence.
        "after_regeneration_rate": _rate([outcome.passes for outcome in outcomes]),
        "after_regeneration_rate_by_level": {
            level: _rate([outcome.passes for outcome in group]) for level, group in by_level.items()
        },
        "regenerations": sum(1 for outcome in outcomes if outcome.attempts > 1),
        "content_words_judged": words,
        "unknown_words": sum(len(outcome.unknown) for outcome in outcomes),
        # Counted on the FIRST attempt: this column answers "what did the gate fire
        # on", and a word that triggered a regeneration is by definition absent from
        # the reply that replaced it. Counting the final text would make the gate
        # invisible in the one place set aside to look at it.
        "most_common_over_level": Counter(
            surface for outcome in outcomes for surface in outcome.first_shot_over_level
        ).most_common(15),
        "unknown_words_first_shot": sum(len(outcome.first_shot_unknown) for outcome in outcomes),
        "results": [
            {
                "scene": outcome.scene,
                "level": outcome.level,
                "turn": outcome.turn,
                "reply": outcome.text,
                "first_shot": outcome.first_shot,
                "attempts": outcome.attempts,
                "judged": outcome.judged,
                "over_level": list(outcome.over_level),
                "first_shot_over_level": list(outcome.first_shot_over_level),
                "first_shot_unknown": list(outcome.first_shot_unknown),
                "far_over_level": list(outcome.far_over_level),
                "unknown": list(outcome.unknown),
                "passes": outcome.passes,
                "first_shot_passes": outcome.first_shot_passes,
            }
            for outcome in outcomes
        ],
    }


def _rate(flags: list[bool]) -> float | None:
    # None rather than 0.0 for an empty group, the same rule the scorer uses: an
    # unmeasured group and a group that scored zero read identically otherwise.
    return sum(flags) / len(flags) if flags else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", choices=sorted(LEVELS), action="append")
    args = parser.parse_args()

    levels = tuple(args.level) if args.level else tuple(LEVELS)
    total = len(levels) * len(SCENES) * TURNS
    print(f"{total} replies over {len(SCENES)} scenes x {len(levels)} levels...")
    outcomes = measure(levels)

    run_id = datetime.now().strftime("%Y%m%d-%H%M")
    record = run_record(outcomes, run_id)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{run_id}-level-compliance.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\nlevel compliance, n={record['n']}")
    print(f"  first shot          {_percent(record['first_shot_rate'])}")
    print(f"  after regeneration  {_percent(record['after_regeneration_rate'])}")
    print(f"  regenerated         {record['regenerations']}")
    for level in record["first_shot_rate_by_level"]:
        first = _percent(record["first_shot_rate_by_level"][level])
        after = _percent(record["after_regeneration_rate_by_level"][level])
        print(f"  {level:16s} first {first}   after {after}")
    print(f"  content words judged  {record['content_words_judged']}")
    print(f"  unknown words         {record['unknown_words']}  (counted as in level)")
    print(f"  most common over level {record['most_common_over_level'][:8]}")
    print(f"\nrun record -> {path}")


def _percent(value: float | None) -> str:
    return "not measured" if value is None else f"{value:.1%}"


if __name__ == "__main__":
    main()
