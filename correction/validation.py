"""Deterministic checks applied to a correction after the model has produced it.

This is the file the "not a thin wrapper" claim rests on (PLAN.md §2-1). Everything
here is ordinary Python run over an answer that already exists — no second call,
no asking the model whether it went too far. That distinction is not stylistic: a
second call would draw the same probabilistic judgement again, and the difference
between the baseline and the real implementation would become "how many times it
was asked" rather than "what was checked".

Being pure post-processing also buys the measurement. The same set of answers can
be scored with the checks on and off, so the effect of a check is isolated with no
extra calls and no sampling noise between the two columns — the difference is the
check and nothing else (.steering/20260810-week2-validation/design.md).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

from config import threshold
from correction.engine import Correction

_DISTANCE_MAX: Final[float] = threshold("rewrite_too_far", "normalised_distance_max")
_SHORT_CHARS: Final[int] = threshold("rewrite_too_far", "short_sentence_chars")
_SHORT_DISTANCE_MAX: Final[int] = threshold("rewrite_too_far", "short_sentence_distance_max")


@dataclass(frozen=True)
class Validation:
    """The correction after checking, and what the checks did to it.

    `discarded` carries the correction that was thrown away rather than a flag.
    A validation node whose rejections cannot be read back is a node that cannot be
    debugged: when the real implementation scores worse than the baseline, the
    first thing to suspect is that it is throwing away corrections that were fine,
    and a boolean cannot answer that.
    """

    correction: Correction
    discarded: Correction | None = None
    reason: str | None = None

    @property
    def fired(self) -> bool:
        return self.discarded is not None


def edit_distance(left: str, right: str) -> int:
    """Character-level Levenshtein distance.

    Written out rather than pulled in: it is fifteen lines, it runs over sentences
    of a dozen characters, and a dependency added for it would have to be justified
    in the Docker image in week 3.
    """
    if left == right:
        return 0
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[j] + 1,  # deletion
                    current[j - 1] + 1,  # insertion
                    previous[j - 1] + (left_char != right_char),  # substitution
                )
            )
        previous = current
    return previous[-1]


def rewritten_too_far(original: str, corrected: str) -> bool:
    """Whether the "correction" is really a different sentence.

    Two rules, because one does not fit both ends of the range. Long sentences are
    judged by the normalised ratio; sentences shorter than `short_sentence_chars`
    are judged by the absolute distance, since changing one character in a
    four-character sentence is 0.25 of it and means almost nothing.

    The thresholds and the measurements behind them are in config/thresholds.toml.
    The important one is that corrections into polite form append long fixed
    endings to short sentences — ありがとう -> ありがとうございます scores 0.50 —
    and that is both the most common correction this app makes and the most
    obviously right one.
    """
    distance = edit_distance(original, corrected)
    if max(len(original), len(corrected)) < _SHORT_CHARS:
        return distance > _SHORT_DISTANCE_MAX
    return distance / max(len(original), len(corrected)) > _DISTANCE_MAX


def validate(learner_sentence: str, correction: Correction) -> Validation:
    """Run the deterministic checks over one correction.

    A discarded correction comes back as `needs_correction: false`. Leaving it as
    `true` with nothing attached would be worse than either alternative: the
    learner is shown nothing, `detection_accuracy` counts it as detected anyway,
    and the object is in a state `parse_correction` refuses to build. Reporting it
    as "no correction needed" at least matches what the learner sees.

    That the choice moves `over_correction_rate` downward on its own is exactly why
    the measurement runs in stages, with and without this file, and why `discarded`
    is written to the run record (design.md, "段は4つに割る").
    """
    if not correction.needs_correction or correction.corrected_sentence is None:
        return Validation(correction=correction)

    if rewritten_too_far(learner_sentence, correction.corrected_sentence):
        return Validation(
            correction=replace(
                correction,
                needs_correction=False,
                corrected_sentence=None,
                reason_en=None,
            ),
            discarded=correction,
            reason="rewrite_too_far",
        )

    return Validation(correction=correction)
