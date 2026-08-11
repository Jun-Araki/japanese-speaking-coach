"""Tests for word splitting.

The vocabulary check is built on top of this, and every failure here shows up
there as a level judgement that cannot be explained. Pinned: which words count as
content, that proper nouns are excluded, that the split unit is the long one, and
that lookup uses the normalised form rather than the surface.
"""

from __future__ import annotations

import pytest

from config import threshold
from nlp import content_words, level_check, tier, words
from nlp.frequency import TIER_TABLES


class TestWords:
    def test_splits_a_sentence_with_no_spaces_in_it(self) -> None:
        # The whole reason this package exists: nothing in the input marks where
        # one word ends and the next begins.
        surfaces = [word.surface for word in words("明日、会議室で資料を確認します。")]

        assert surfaces == ["明日", "、", "会議室", "で", "資料", "を", "確認", "し", "ます", "。"]

    def test_keeps_a_compound_whole(self) -> None:
        # Split mode C. A learner meets 会議室 as one thing; scoring 会議 and 室
        # separately would report it as two easy words.
        assert [word.surface for word in words("会議室")] == ["会議室"]

    def test_normalises_inflection_and_script(self) -> None:
        # "Has the learner met this word?" is a question about 行く, not about the
        # form it happens to appear in.
        assert [word.normalized for word in words("行った")][0] == "行く"
        assert [word.normalized for word in words("居ます")][0] == "居る"


class TestContentWords:
    def test_drops_particles_and_auxiliaries(self) -> None:
        # These appear in every sentence at every level. Counting them would drag
        # any over-level ratio toward zero and pass a reply that is in fact hard.
        surfaces = [word.surface for word in content_words("明日、会議室で資料を確認します。")]

        assert "で" not in surfaces
        assert "を" not in surfaces
        assert "ます" not in surfaces

    def test_keeps_nouns_verbs_adjectives_and_adverbs(self) -> None:
        surfaces = [word.surface for word in content_words("とても難しい問題をゆっくり読みます。")]

        assert "問題" in surfaces  # noun
        assert "読み" in surfaces  # verb
        assert "難しい" in surfaces  # adjective
        assert "ゆっくり" in surfaces  # adverb

    def test_drops_proper_nouns(self) -> None:
        # A name has no difficulty tier, and self-introduction and workplace scenes
        # cannot avoid them. Judging 田中 as unknown vocabulary would fire the check
        # on every reply that addresses the learner's colleague.
        surfaces = [word.surface for word in content_words("田中さんはバンガロールにいます。")]

        assert "田中" not in surfaces
        assert "バンガロール" not in surfaces

    def test_drops_numerals(self) -> None:
        # The frequency list spells numbers out (一, 二, 三) and the tokenizer leaves
        # digits as digits, so 六時 and 25 came back as words the learner has never
        # met. Four of the fifteen unmatched words across the whole evaluation set
        # were numerals.
        surfaces = [word.surface for word in content_words("私は毎朝六時に起きます。")]

        assert "六" not in surfaces
        assert "起き" in surfaces

    def test_the_part_of_speech_lists_are_not_inlined(self) -> None:
        # Same rule as every other threshold: a list that can be edited in a source
        # file produces README numbers nobody can reproduce (docs/ja/glossary.md §7).
        assert threshold("vocabulary_level", "content_pos") == ["名詞", "動詞", "形容詞", "副詞"]
        assert threshold("vocabulary_level", "exempt_pos") == ["名詞,固有名詞", "名詞,数詞"]


needs_tiers = pytest.mark.skipif(
    not all(path.exists() for path in TIER_TABLES.values()),
    reason="frequency tables are fetched, not committed: python -m nlp.frequency --build",
)


@needs_tiers
class TestTier:
    def test_a_compound_is_looked_up_whole_before_it_is_taken_apart(self) -> None:
        """The bug this ordering exists to prevent, pinned as a comparison.

        The tokenizer keeps 会議室 whole and the SHORT-unit list does not contain
        it, so the first version fell straight through to max(会議, 室). 室 barely
        occurs on its own, which made an everyday word score as top-tier
        vocabulary. Asserting the tier is below 室's own tier says that without
        hard-coding a number that the next corpus release would move.
        """
        compound = [word for word in content_words("会議室") if word.surface == "会議室"][0]
        room = [word for word in content_words("室") if word.surface == "室"][0]

        assert tier(compound) is not None
        assert tier(room) is not None
        assert tier(compound) < tier(room)  # type: ignore[operator]


@needs_tiers
class TestLevelCheck:
    def test_an_everyday_sentence_passes_for_a_beginner(self) -> None:
        result = level_check("明日の会議室で資料を確認します。", "beginner")

        assert result.passes
        assert result.over_level == ()

    def test_business_keigo_fails_for_a_beginner_and_says_which_words(self) -> None:
        result = level_check("弊社の懸案事項につきましては、鋭意検討いたします。", "beginner")

        assert not result.passes
        assert "弊社" in [word.surface for word in result.over_level]
        # Naming the words is the point: a reply rejected without them cannot be
        # debugged, and week 4 will want to know whether the same handful keeps
        # triggering regeneration.
        assert result.far_over_level != ()

    def test_the_same_sentence_is_allowed_higher_up(self) -> None:
        # The check has to discriminate between levels, not just between sentences.
        result = level_check("弊社の懸案事項につきましては、鋭意検討いたします。", "intermediate")

        assert result.passes

    def test_a_reply_with_no_content_words_is_not_over_level(self) -> None:
        # "はい。" divides by zero if the ratio is written carelessly, and the answer
        # is a measured zero rather than an absent measurement.
        result = level_check("はい。", "beginner")

        assert result.judged == 0
        assert result.ratio == 0.0
        assert result.passes
