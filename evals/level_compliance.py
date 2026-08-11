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

Nothing here is regenerated yet: the validation node arrives on day 4, so today's
run measures the raw side only, and that is stated in the record rather than left
to be inferred from the date.

Run:  .venv/bin/python -m evals.level_compliance
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from dialogue import Utterance, opening_line, reply
from dialogue.reply import PROMPT_VERSION, TEMPERATURE
from dialogue.scenes import LEVELS, SCENES
from evals.score import RUNS_DIR
from evals.script import SCRIPT, TURNS
from llm import active_model_name
from nlp import level_check

# The tier tables and the mapping from level to tier are as much a part of this
# number as the prompt is. A run measured before the mapping was calibrated is not
# comparable with one measured after, and only this file knows to say so.
TIER_VERSION: Final = "bccwj-suw+luw-cuts70-80-90-95"


@dataclass(frozen=True)
class ReplyOutcome:
    scene: str
    level: str
    turn: int
    text: str
    judged: int
    over_level: tuple[str, ...]
    far_over_level: tuple[str, ...]
    unknown: tuple[str, ...]
    passes: bool


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
                text = reply(scene, level, history)
                history.append(Utterance("partner", text))
                check = level_check(text, level)
                outcomes.append(
                    ReplyOutcome(
                        scene=scene,
                        level=level,
                        turn=turn,
                        text=text,
                        judged=check.judged,
                        over_level=tuple(word.surface for word in check.over_level),
                        far_over_level=tuple(word.surface for word in check.far_over_level),
                        unknown=tuple(word.surface for word in check.unknown),
                        passes=check.passes,
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
        "regenerated": False,
        "trials": 1,
        "n": len(outcomes),
        "date": run_id[:8],
        "first_shot_rate": _rate([outcome.passes for outcome in outcomes]),
        "first_shot_rate_by_level": {
            level: _rate([outcome.passes for outcome in group]) for level, group in by_level.items()
        },
        "content_words_judged": words,
        "unknown_words": sum(len(outcome.unknown) for outcome in outcomes),
        "most_common_over_level": Counter(
            surface for outcome in outcomes for surface in outcome.over_level
        ).most_common(15),
        "results": [
            {
                "scene": outcome.scene,
                "level": outcome.level,
                "turn": outcome.turn,
                "reply": outcome.text,
                "judged": outcome.judged,
                "over_level": list(outcome.over_level),
                "far_over_level": list(outcome.far_over_level),
                "unknown": list(outcome.unknown),
                "passes": outcome.passes,
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

    overall = _percent(record["first_shot_rate"])
    print(f"\nfirst-shot level compliance  {overall}  (n={record['n']})")
    for level, rate in record["first_shot_rate_by_level"].items():
        print(f"  {level:16s} {_percent(rate)}")
    print(f"  content words judged  {record['content_words_judged']}")
    print(f"  unknown words         {record['unknown_words']}  (counted as in level)")
    print(f"  most common over level {record['most_common_over_level'][:8]}")
    print(f"\nrun record -> {path}")


def _percent(value: float | None) -> str:
    return "not measured" if value is None else f"{value:.1%}"


if __name__ == "__main__":
    main()
