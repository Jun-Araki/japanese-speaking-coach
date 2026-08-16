"""Splitting Japanese into words, and picking out the ones that carry difficulty.

Japanese writes no spaces between words, so "does this reply use vocabulary above
the learner's level?" cannot be answered by string matching: the boundary the
question depends on is not written down. Everything else in `nlp/` stands on this
file (see docs/en/architecture.md).

Only content words are counted. Particles and auxiliaries are the most frequent
words in the language and appear in every sentence at every level, so including
them would drag any ratio toward zero and let a genuinely hard reply pass. The
part-of-speech list lives in config/thresholds.toml, not here.

Split mode C is the longest of Sudachi's three: 会議室 stays one word rather than
becoming 会議 + 室. That is the right unit for this question — a learner meets
会議室 as one thing, and scoring its halves would call it two easy words.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Final

from sudachipy import Dictionary, SplitMode

from config import threshold

_CONTENT_POS: Final[tuple[str, ...]] = tuple(threshold("vocabulary_level", "content_pos"))
_EXEMPT_POS: Final[tuple[str, ...]] = tuple(threshold("vocabulary_level", "exempt_pos"))


@dataclass(frozen=True)
class Word:
    """One word of a reply, in the form the level check needs it.

    `normalized` rather than `surface` is what gets looked up: 行った, 行きます and
    いった are one word for the purpose of "has the learner met this?", and Sudachi
    already knows how to collapse them. Keeping the surface too is what makes a
    rejected reply explainable — a learner is told about 承知, not about 承知する.
    """

    surface: str
    normalized: str
    pos: tuple[str, ...]
    # The word split again at Sudachi's shortest unit, when it is a compound.
    # 会議室 stays one word for counting, but the frequency list is a SHORT-unit
    # list and does not contain it, so the parts are what make it findable. Empty
    # when the word does not decompose.
    parts: tuple[str, ...]

    @property
    def is_content(self) -> bool:
        """Whether this word carries meaning a learner has to know.

        The check is on the major class only. Sudachi's second field distinguishes
        普通名詞 from 固有名詞 and 非自立可能, which matters for the exemption below
        but not for deciding that a noun is a noun.
        """
        return bool(self.pos) and self.pos[0] in _CONTENT_POS

    @property
    def is_exempt(self) -> bool:
        """Whether the word is excluded from the level check regardless of anything.

        Proper nouns: 田中, バンガロール, インド. No difficulty tier means anything for
        a name, and self-introduction and workplace scenes cannot avoid them. Left
        in the token stream rather than dropped at tokenisation, so a reply that is
        mostly names is still visibly mostly names.
        """
        joined = ",".join(self.pos)
        return any(joined.startswith(prefix) for prefix in _EXEMPT_POS)


@lru_cache(maxsize=1)
def _tokenizer() -> Any:
    """One dictionary for the process.

    Loading SudachiDict takes a second or two and about 70MB. A reply is checked on
    every conversation turn, and the level measurement runs it ninety times in a
    row, so building it per call would dominate both.
    """
    return Dictionary().create()


def words(text: str) -> list[Word]:
    """Every word in the text, in order, including particles and punctuation."""
    tokenizer = _tokenizer()
    morphemes = tokenizer.tokenize(text, SplitMode.C)
    return [
        Word(
            surface=morpheme.surface(),
            normalized=morpheme.normalized_form(),
            pos=tuple(part for part in morpheme.part_of_speech() if part != "*"),
            parts=_short_units(morpheme),
        )
        for morpheme in morphemes
    ]


def _short_units(morpheme: Any) -> tuple[str, ...]:
    """The morpheme re-split at unit A, or nothing if it does not decompose.

    Read at tokenisation rather than on demand so that `Word` stays a plain value
    and nothing downstream needs the dictionary open.
    """
    units = morpheme.split(SplitMode.A)
    if len(units) < 2:
        return ()
    return tuple(unit.normalized_form() for unit in units)


def content_words(text: str) -> list[Word]:
    """The words the level check is allowed to judge.

    Proper nouns are dropped here rather than scored and forgiven later, so that a
    reply of "田中さんは会議室にいます" is judged on 会議室 and not diluted by 田中.
    """
    return [word for word in words(text) if word.is_content and not word.is_exempt]
