"""Deterministic checks applied to a correction after the model has produced it.

This is the file the "not a thin wrapper" claim rests on (see
docs/en/functional-design.md). Everything
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
from dialogue.scenes import politeness_floor

# Frozen before the measurement it will be judged by, which is the whole of what
# "pre-registered" means here. The day-2 error analysis found that the baseline
# often admits the sentence was fine and rewrites it anyway, and that admission
# separates the two labels better than anything else tried: on dev, 54.5% of the
# over-corrections say one of these against 19.4% of the genuine corrections.
#
# The set is written out because the separation moves with it. Three of these four
# give +23.5pt, all four give +35.2pt, and a looser match on "understandable" alone
# gives +47.5pt — against an acceptance bar of 20pt and a denominator of eleven,
# where one item is 9.1pt. A criterion fixed in advance against a predicate chosen
# afterwards is not a criterion. Change this list and the run that used it is no
# longer the run the bar was set for.
ADMISSION_PHRASES: Final[tuple[str, ...]] = (
    "grammatically correct",
    "grammatically understandable",
    "perfectly natural",
    "is correct",
)

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


def admits_the_sentence_was_fine(reason: str) -> bool:
    """Whether the model's own explanation concedes the original needed nothing.

    Deterministic, and about the model's output rather than the learner's sentence:
    this reads what was already written, it does not ask anything further. Whether
    it earns a place in the validation node is decided on 8/15 against the bar in
    design.md, on the real implementation's reasons rather than the baseline's.
    """
    lowered = reason.lower()
    return any(phrase in lowered for phrase in ADMISSION_PHRASES)


# The other candidate for check 3, and the one tried first. A sentence that ends
# in a polite form was probably fine as it stood — except at tier A, where politeness
# is not required at all and the plain form IS the right answer (docs/ja/glossary.md
# §2). Measured on the 120 items: without the tier the predicate separates the labels
# by MINUS 7.8 points, firing more often on the sentences that genuinely needed
# correcting than on the ones that did not. Reading the tier first takes it to
# +12.2, which is real and is still not much.
#
# Only the tier is read, never `politeness_rule` or POLITENESS_ADJUDICATIONS: those
# settle borderline cases by quoting evaluation items, one of them from the held-out
# split, and a rule built from an item is a rule that answers that item.
POLITE_ENDINGS: Final[tuple[str, ...]] = (
    "です",
    "ます",
    "ください",
    "でしょうか",
    "ました",
    "ません",
    "でした",
    "ですか",
    "ますか",
    "ですね",
    "ませんか",
    "でしょう",
    "ましょう",
)

_CLOSING = "。、？！「」 \t\n"


def politeness_looks_sufficient(sentence: str, scene: str) -> bool:
    """Whether the sentence already meets what the scene asks for, structurally.

    Tier A asks for nothing, so everything passes; tiers B and C are judged on the
    ending alone. No exceptions for 「はじめまして」 or a trailing 「お名前は」 — both
    are correct and both fail this test. They are left failing on purpose: an
    exception list here would be copied out of the evaluation set, and a predicate
    that knows the answers is not measuring anything. The error it causes is a
    measurable error; the one an exception list causes is not.
    """
    tier, _ = politeness_floor(scene)
    if tier == "A":
        return True
    return sentence.rstrip(_CLOSING).endswith(POLITE_ENDINGS)


def edit_distance(left: str, right: str) -> int:
    """Character-level Levenshtein distance.

    Written out rather than pulled in: it is fifteen lines, it runs over sentences
    of a dozen characters, and a dependency added for it would have to be justified
    in the Docker image when the API is containerised.
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
