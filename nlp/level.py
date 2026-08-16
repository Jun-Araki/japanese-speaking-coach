"""Deciding whether a reply sits above the learner's level.

Two rules, both from config/thresholds.toml. A reply fails if too large a share of
its content words are above the learner's tier, and it fails outright if any one
word is far above it — a single incomprehensible word can cost a beginner the
whole sentence, however good the rest of the ratio looks.

Words the frequency list does not contain are counted as IN level, and counted
separately as well. That is the generous reading, and it is the same shape as
`unusable_verdicts` in the scorer: when a rule has to guess, the guess goes in the
direction that does not manufacture failures, and the number of guesses is
reported next to the result instead of being left implicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from config import threshold
from nlp.frequency import BEYOND, LEVEL_TIER, tiers
from nlp.tokenize import Word, content_words

_RATIO_MAX: Final[float] = threshold("vocabulary_level", "over_level_ratio_max")
_GAP_MAX: Final[int] = threshold("vocabulary_level", "absolute_tier_gap_max")


@dataclass(frozen=True)
class LevelCheck:
    """What the check found, in a form that can be explained to a learner.

    `over_level` carries the words themselves rather than only a count: a reply
    rejected without naming the word that failed cannot be debugged, and it is
    worth knowing whether regeneration fires on the same handful of words every
    time.
    """

    words: tuple[Word, ...]
    over_level: tuple[Word, ...]
    far_over_level: tuple[Word, ...]
    unknown: tuple[Word, ...]

    @property
    def judged(self) -> int:
        """Content words that were actually looked up — the denominator."""
        return len(self.words)

    @property
    def ratio(self) -> float:
        # A reply with no content words at all ("はい。") is not over level. Zero
        # rather than a division, and deliberately not None: unlike an unmeasured
        # metric, this one has an answer.
        return len(self.over_level) / self.judged if self.judged else 0.0

    @property
    def passes(self) -> bool:
        return not self.far_over_level and self.ratio <= _RATIO_MAX


def tier(word: Word) -> int | None:
    """The word's difficulty tier, or None if neither list has it.

    Three passes, in the order that gets the unit right rather than the order that
    is fastest.

    1. The short-unit table, which covers ordinary single words.
    2. The long-unit table, for compounds. The tokenizer is asked for its longest
       unit so 会議室 stays one word, and the short-unit list does not contain it.
    3. Only then, the word split at unit A and judged by its hardest piece.

    The third pass used to be the second, and it was wrong in a way that only
    showed up when a real sentence was run through: 会議室 became max(会議, 室), and
    室 barely occurs on its own, so an everyday word came out as top-tier
    vocabulary. A compound is at least as hard as its hardest piece — but only when
    nothing knows the compound itself.
    """
    short = tiers("suw")
    for key in (word.normalized, word.surface):
        found = short.get(key)
        if found is not None:
            return found

    long_unit = tiers("luw")
    for key in (word.normalized, word.surface):
        found = long_unit.get(key)
        if found is not None:
            return found

    if not word.parts:
        return None
    part_tiers = [short.get(part) for part in word.parts]
    if any(found is None for found in part_tiers):
        return None
    return max(found for found in part_tiers if found is not None)


def level_check(text: str, level: str) -> LevelCheck:
    """Judge one reply against one learner level."""
    allowed = LEVEL_TIER[level]
    judged: list[Word] = []
    over: list[Word] = []
    far: list[Word] = []
    unknown: list[Word] = []

    for word in content_words(text):
        judged.append(word)
        found = tier(word)
        if found is None:
            unknown.append(word)
            continue
        if found > allowed:
            over.append(word)
            if found - allowed >= _GAP_MAX:
                far.append(word)

    return LevelCheck(
        words=tuple(judged),
        over_level=tuple(over),
        far_over_level=tuple(far),
        unknown=tuple(unknown),
    )


__all__ = ["BEYOND", "LevelCheck", "level_check", "tier"]
