"""Tests for the parts of the conversation partner that do not call the model.

The reply itself is not tested here: asserting on generated Japanese would either
be so loose it catches nothing or so tight it fails on a harmless rewording. What
is testable is the ceiling on reply length, which is an acceptance condition for
week 1, and the scene and level tables, which label evaluation data and so must
not drift from docs/ja/glossary.md.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any

import pytest

from dialogue import Utterance
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

# `dialogue/__init__.py` re-exports the function `reply`, which overwrites the
# submodule attribute of the same name — so `import dialogue.reply as ...` binds
# the function, not the module, and monkeypatching it fails with a message that
# does not say why. Week 1 hit this collision with `correction.check` and renamed
# the module to `engine`; here the public call is `dialogue.reply()` and stays, so
# the test asks sys.modules instead.
reply_module = importlib.import_module("dialogue.reply")


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

    def test_the_tier_of_each_scene_is_the_one_the_dataset_was_labelled_under(self) -> None:
        """Tiers reach the generator as `tier {tier}` and decided 120 labels.

        Fixed here rather than left to the table: moving a scene between tiers makes
        every item already labelled under it wrong, and nothing else would notice —
        the same reason the scene identifiers themselves are pinned (§2, §3).
        """
        assert {scene: tier for scene, (tier, _) in POLITENESS_FLOORS.items()} == {
            "greeting": "A",
            "thanks": "A",
            "self_introduction": "B",
            "simple_request": "B",
            "delay_notice": "C",
            "workplace_keigo": "C",
        }

    def test_the_scenes_that_needed_adjudicating_are_the_ones_that_split(self) -> None:
        """Tier B is where the candidates split; A and C never did (§2).

        Without this the other tests here pass over an empty dict: they all iterate
        `POLITENESS_ADJUDICATIONS`, so deleting its contents — which takes the worked
        criteria out of the generator's prompt — is invisible.
        """
        assert set(POLITENESS_ADJUDICATIONS) == {"self_introduction", "simple_request"}
        for adjudication in POLITENESS_ADJUDICATIONS.values():
            assert adjudication.strip()

    def test_unknown_scene_is_rejected_by_both(self) -> None:
        with pytest.raises(ValueError, match="Unknown scene"):
            politeness_floor("restaurant")
        with pytest.raises(ValueError, match="Unknown scene"):
            politeness_rule("restaurant")


class TestLooksJapanese:
    """The reply has to be in Japanese, and quoting the learner does not count.

    Both replies this was written for began "THOUGHT: The user said ..." and quoted
    the learner's sentence, so a presence test passes them. The two populations do
    not overlap: 88 sound replies scored 1.000 and the two leaks scored 0.323 and
    0.064 (config/thresholds.toml).
    """

    def test_a_japanese_reply_passes(self) -> None:
        assert reply_module.looks_japanese("はい、元気です。")

    def test_reasoning_that_quotes_the_learner_does_not(self) -> None:
        leaked = 'THOUGHT: The user said "はい、確認してから送ります。" This does not answer.'

        assert not reply_module.looks_japanese(leaked)

    def test_a_reply_with_neither_script_does_not(self) -> None:
        # Punctuation, an empty string. Not Japanese, and worth another attempt.
        assert not reply_module.looks_japanese("……")


class TestCheckedReply:
    """Validation node 2: regenerate once when the reply is above the learner.

    The gate and the metric share `level_check`, so the figure after regeneration
    is the share that failed twice. That is why the first attempt is kept and
    reported separately (docs/ja/glossary.md §5), and why these tests care about
    what is returned alongside the text as much as the text itself.
    """

    def _model(self, monkeypatch: Any, *answers: str) -> list[list[Any]]:
        """Replace the provider with a scripted one, recording what it was sent."""
        sent: list[list[Any]] = []
        replies = list(answers)

        class ScriptedModel:
            def invoke(self, messages: list[Any]) -> Any:
                sent.append(list(messages))
                return SimpleNamespace(content=replies.pop(0))

        monkeypatch.setattr(reply_module, "build_chat_model", lambda temperature: ScriptedModel())
        return sent

    def test_an_in_level_reply_is_returned_untouched_and_costs_one_call(
        self, monkeypatch: Any
    ) -> None:
        sent = self._model(monkeypatch, "はい、元気です。")

        result = reply_module.checked_reply("greeting", "beginner", [Utterance("learner", "やあ")])

        assert result.text == "はい、元気です。"
        assert result.attempts == 1
        assert result.regenerated is False
        assert result.over_level == ()
        assert len(sent) == 1

    def test_an_over_level_reply_is_asked_for_again(self, monkeypatch: Any) -> None:
        self._model(monkeypatch, "弊社の懸案事項を鋭意検討します。", "はい、考えます。")

        result = reply_module.checked_reply(
            "workplace_keigo", "beginner", [Utterance("learner", "どうですか")]
        )

        assert result.text == "はい、考えます。"
        assert result.attempts == 2
        assert result.regenerated is True

    def test_the_first_attempt_survives_the_retry(self, monkeypatch: Any) -> None:
        # The compliance metric needs the ungated reply. If the retry overwrote it,
        # the only figure left would be the one the gate produced, and glossary §5
        # asks for both.
        self._model(monkeypatch, "弊社の懸案事項を鋭意検討します。", "はい、考えます。")

        result = reply_module.checked_reply(
            "workplace_keigo", "beginner", [Utterance("learner", "どうですか")]
        )

        assert result.first_shot == "弊社の懸案事項を鋭意検討します。"
        assert "弊社" in result.first_shot_over_level
        # And the final text is judged on its own, not left carrying the words that
        # triggered the retry. The learner got a reply with none of them in it.
        assert result.over_level == ()

    def test_the_retry_names_the_words_rather_than_asking_again(self, monkeypatch: Any) -> None:
        # At temperature 0.7 a bare retry sometimes succeeds by luck, which is a
        # different mechanism from the one being claimed. Week 1 fixed the same
        # point on the correction side.
        sent = self._model(monkeypatch, "弊社の懸案事項を鋭意検討します。", "はい、考えます。")

        reply_module.checked_reply(
            "workplace_keigo", "beginner", [Utterance("learner", "どうですか")]
        )

        retry_prompt = sent[1][-1].content
        assert "弊社" in retry_prompt
        assert "鋭意" in retry_prompt

    def test_it_gives_up_rather_than_looping(self, monkeypatch: Any) -> None:
        # Both attempts are above level. A partner that never answers costs the
        # learner more than a slightly hard sentence does.
        sent = self._model(
            monkeypatch, "弊社の懸案事項を鋭意検討します。", "弊社の懸案事項を鋭意検討します。"
        )

        result = reply_module.checked_reply(
            "workplace_keigo", "beginner", [Utterance("learner", "どうですか")]
        )

        assert result.text == "弊社の懸案事項を鋭意検討します。"
        assert len(sent) == 2
        # Still over level, and said so. The retry was spent and did not work,
        # which is a different outcome from the retry not being needed.
        assert "弊社" in result.over_level

    def test_english_reasoning_is_sent_back_before_vocabulary_is_judged(
        self, monkeypatch: Any
    ) -> None:
        # The level check happily read `should` and `they` as words above the
        # learner's level. Asking whether the reply is Japanese has to come first,
        # or the vocabulary metric ends up counting English.
        leaked = 'THOUGHT: The user seems to be ending the conversation. I need to acknowledge.'
        self._model(monkeypatch, leaked, "はい、また明日。")

        result = reply_module.checked_reply(
            "greeting", "beginner", [Utterance("learner", "また明日")]
        )

        assert result.text == "はい、また明日。"
        assert result.language_retried is True
        # Counted apart from the level gate: different fault, different fix.
        assert result.attempts == 1

    def test_a_japanese_reply_is_not_sent_back(self, monkeypatch: Any) -> None:
        self._model(monkeypatch, "はい、元気です。")

        result = reply_module.checked_reply(
            "greeting", "beginner", [Utterance("learner", "やあ")]
        )

        assert result.language_retried is False

    def test_attempts_is_counted_rather_than_assumed(self, monkeypatch: Any) -> None:
        # It used to return `1 + MAX_REGENERATIONS` on every failure path — a
        # constant in the shape of a measurement. With the limit at one the two
        # agree, which is why nothing caught it; the count is what is meant.
        self._model(monkeypatch, "弊社の懸案事項を鋭意検討します。", "はい、考えます。")
        rescued = reply_module.checked_reply(
            "workplace_keigo", "beginner", [Utterance("learner", "どうですか")]
        )

        self._model(monkeypatch, "はい、元気です。")
        clean = reply_module.checked_reply(
            "greeting", "beginner", [Utterance("learner", "やあ")]
        )

        assert (clean.attempts, rescued.attempts) == (1, 2)

    def test_reply_still_returns_a_string(self, monkeypatch: Any) -> None:
        # app/ and the measurement script both call `reply`; adding the gate must
        # not change what they get.
        self._model(monkeypatch, "はい、元気です。")

        assert reply_module.reply("greeting", "beginner", [Utterance("learner", "やあ")]) == (
            "はい、元気です。"
        )
