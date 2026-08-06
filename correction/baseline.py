"""The baseline: one call, nothing around it.

This is the naive implementation the comparison table in the README measures the
real one against — "correct this Japanese and tell me why", asked once. No
criteria, no rule about what to do when unsure, no retry, no validation node, no
retrieval, no tokenisation.

It is deliberately not made good. A carefully written baseline narrows the gap the
rest of the project exists to create, and the number stops meaning anything. But
two things are held equal on purpose:

  - It gets the SAME INPUTS as the real engine: the sentence, the scene and the
    level. Withholding the scene would be cheating in the other direction — the
    labels themselves depend on who is being spoken to (docs/ja/glossary.md §2),
    so a baseline that does not know the scene loses points for missing
    information rather than for being naive, and the table would then be
    measuring what we told it rather than what we built.
  - It produces the SAME JSON. Not because a naive implementation would, but
    because a second output format means a second scoring path, and a bug in
    either one is indistinguishable from a difference between the two
    implementations.

Measured before the validation node exists, per docs/ja/glossary.md §7: a baseline
written after the real thing is a baseline written by someone who already knows
the answer.
"""

from __future__ import annotations

from typing import Final

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from correction.engine import (
    CorrectionFormatError,
    CorrectionResult,
    format_problems,
    parse_correction,
)
from dialogue.scenes import level_brief, scene_brief
from llm import as_text, build_chat_model

PROMPT_VERSION: Final = "baseline-v1"

# Same as the engine. The comparison is between the implementations, so anything
# that would move the numbers on its own has to be identical on both sides.
TEMPERATURE: Final = 0.0

# One call. The retry is part of what was built, not part of the naive version, so
# it belongs on the other side of the table.
ATTEMPTS: Final = 1

SYSTEM_PROMPT: Final = """\
Correct this Japanese sentence written by someone learning Japanese, and explain \
why in English.

The situation: {situation}
Their level: {level}

Answer with this JSON object:

{{"needs_correction": true or false,
  "corrected_sentence": "the corrected sentence" or null,
  "reason_en": "why, in English" or null,
  "grounding_ids": []}}
"""


def baseline_check(sentence: str, scene: str, level: str) -> CorrectionResult:
    """Judge one learner sentence the naive way.

    The signature matches `correction.check` so that the scoring script calls both
    through one code path.
    """
    role, _ = scene_brief(scene)
    model = build_chat_model(temperature=TEMPERATURE)
    messages: list[BaseMessage] = [
        SystemMessage(SYSTEM_PROMPT.format(situation=role, level=level_brief(level))),
        HumanMessage(sentence),
    ]

    answer = as_text(model.invoke(messages).content)
    try:
        correction = parse_correction(answer)
    except CorrectionFormatError:
        # Counted, not hidden: a baseline that cannot hold the format is a real
        # finding about the baseline (docs/ja/glossary.md §5).
        return CorrectionResult(sentence, None, ATTEMPTS, ("invalid_json",))

    return CorrectionResult(sentence, correction, ATTEMPTS, format_problems(correction))
