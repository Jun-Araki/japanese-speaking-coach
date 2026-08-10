"""Tests for the parts of the conversation partner that do not call the model.

The reply itself is not tested here: asserting on generated Japanese would either
be so loose it catches nothing or so tight it fails on a harmless rewording. What
is testable is the ceiling on reply length, which is an acceptance condition for
week 1, and the scene and level tables, which label evaluation data and so must
not drift from docs/ja/glossary.md.
"""

from __future__ import annotations

import pytest

from dialogue.reply import MAX_SENTENCES, limit_sentences
from dialogue.scenes import (
    LEVEL_BRIEFS,
    LEVELS,
    POLITENESS_ADJUDICATIONS,
    POLITENESS_FLOORS,
    SCENE_BRIEFS,
    SCENES,
    level_brief,
    politeness_floor,
    politeness_rule,
    scene_brief,
)


class TestLimitSentences:
    def test_keeps_a_single_sentence(self) -> None:
        assert limit_sentences("おはようございます。") == "おはようございます。"

    def test_keeps_two_sentences(self) -> None:
        text = "おはようございます。いい天気ですね。"
        assert limit_sentences(text) == text

    def test_drops_the_third_sentence(self) -> None:
        text = "元気ですか。それは良かったです。どこかへお出かけですか。"
        assert limit_sentences(text) == "元気ですか。それは良かったです。"

    def test_drops_a_trailing_fragment(self) -> None:
        # A cut-off tail would read as the partner being interrupted.
        assert limit_sentences("はい。そうですね。それで") == "はい。そうですね。"

    def test_keeps_an_unpunctuated_line_whole(self) -> None:
        assert limit_sentences("おはよう") == "おはよう"

    @pytest.mark.parametrize("ending", ["。", "！", "？", "!", "?"])
    def test_counts_every_sentence_ending(self, ending: str) -> None:
        text = f"あ{ending}い{ending}う{ending}"
        assert limit_sentences(text) == f"あ{ending}い{ending}"

    def test_respects_an_explicit_maximum(self) -> None:
        text = "あ。い。う。"
        assert limit_sentences(text, maximum=1) == "あ。"

    def test_default_maximum_matches_the_documented_limit(self) -> None:
        assert MAX_SENTENCES == 2


class TestScenesAndLevels:
    def test_every_scene_has_a_brief_and_an_opening(self) -> None:
        assert set(SCENES) == set(SCENE_BRIEFS)
        for scene in SCENES:
            role, opening = scene_brief(scene)
            assert role and opening

    def test_every_level_has_a_brief(self) -> None:
        assert set(LEVELS) == set(LEVEL_BRIEFS)
        for level in LEVELS:
            assert level_brief(level)

    def test_scene_identifiers_match_the_glossary(self) -> None:
        # Ordered easiest first; these identifiers label evaluation data, so a
        # rename here silently invalidates every item already labelled.
        assert list(SCENES) == [
            "greeting",
            "self_introduction",
            "thanks",
            "simple_request",
            "delay_notice",
            "workplace_keigo",
        ]

    def test_level_identifiers_match_the_glossary(self) -> None:
        assert list(LEVELS) == ["beginner", "upper_beginner", "intermediate"]

    def test_unknown_scene_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown scene"):
            scene_brief("restaurant")

    def test_unknown_level_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown level"):
            level_brief("advanced")


class TestPolitenessFloor:
    """The floor is split in two, and which half a caller gets is a measurement decision.

    The worked cases quote evaluation items with the dataset's verdict attached, so
    they belong in a labelling prompt and nowhere a human rater can read them. On
    2026-08-09 they were in the one string both used, and the rater's form printed
    the answer to an item it was asking about (docs/ja/glossary.md §5).
    """

    def test_the_floor_shown_to_people_cites_no_evaluation_item(self) -> None:
        for scene in SCENES:
            _, floor = politeness_floor(scene)
            for adjudication in POLITENESS_ADJUDICATIONS.values():
                assert adjudication not in floor

    def test_the_labelling_rule_keeps_everything_the_floor_says(self) -> None:
        """Splitting must not quietly thin the criteria the generator is given."""
        for scene in SCENES:
            tier, floor = politeness_floor(scene)
            rule_tier, rule = politeness_rule(scene)
            assert rule_tier == tier
            assert floor in rule
            assert POLITENESS_ADJUDICATIONS.get(scene, "") in rule

    def test_a_scene_with_no_worked_cases_gets_the_floor_unchanged(self) -> None:
        assert politeness_rule("greeting") == politeness_floor("greeting")

    def test_every_scene_has_a_floor(self) -> None:
        assert set(POLITENESS_FLOORS) == set(SCENES)

    def test_unknown_scene_is_rejected_by_both(self) -> None:
        with pytest.raises(ValueError, match="Unknown scene"):
            politeness_floor("restaurant")
        with pytest.raises(ValueError, match="Unknown scene"):
            politeness_rule("restaurant")
