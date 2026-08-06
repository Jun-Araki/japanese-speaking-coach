"""Tests for the parts of the correction that do not depend on the model's judgement.

Whether a given sentence really needs correcting is measured against the evaluation
data (day 5), not asserted here. What is tested here is everything the measurement
itself rests on: that a broken answer is recognised as broken, that a retry cannot
quietly repair the format metric, and that a reason written in Japanese is counted
as a format failure rather than a wrong judgement. A bug in any of those looks
exactly like a bad model, which is the confusion docs/ja/glossary.md §5 exists to
prevent.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from config import threshold
from correction import engine
from correction.engine import (
    MAX_ATTEMPTS,
    TEMPERATURE,
    Correction,
    CorrectionFormatError,
    check,
    japanese_left_unquoted,
    parse_correction,
    reason_is_english,
)

VALID_ANSWER = json.dumps(
    {
        "needs_correction": True,
        "corrected_sentence": "おはようございます",
        "reason_en": "The polite morning greeting is a fixed phrase.",
        "grounding_ids": [],
    },
    ensure_ascii=False,
)


class FakeModel:
    """Returns the given answers in order, one per invoke."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.calls: list[list[Any]] = []

    def invoke(self, messages: list[Any]) -> Any:
        # Copied: the caller appends to the same list between attempts, so keeping
        # the reference would make every recorded call look identical.
        self.calls.append(list(messages))
        return type("FakeAnswer", (), {"content": self.answers.pop(0)})()


@pytest.fixture
def fake_model(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(*answers: str) -> FakeModel:
        model = FakeModel(*answers)
        monkeypatch.setattr(engine, "build_chat_model", lambda temperature: model)
        return model

    return install


class TestParseCorrection:
    def test_parses_a_plain_object(self) -> None:
        result = parse_correction(VALID_ANSWER)
        assert result == Correction(
            needs_correction=True,
            corrected_sentence="おはようございます",
            reason_en="The polite morning greeting is a fixed phrase.",
            grounding_ids=(),
        )

    def test_parses_an_object_inside_a_markdown_fence(self) -> None:
        assert parse_correction(f"```json\n{VALID_ANSWER}\n```").needs_correction is True

    def test_parses_an_object_wrapped_in_commentary(self) -> None:
        answer = f"Here is my judgement:\n{VALID_ANSWER}\nHope that helps."
        assert parse_correction(answer).corrected_sentence == "おはようございます"

    def test_a_false_judgement_carries_no_correction(self) -> None:
        # Whatever the model puts in these fields, there is nothing to show for a
        # sentence that was already fine.
        answer = json.dumps(
            {
                "needs_correction": False,
                "corrected_sentence": "ありがとうございます",
                "reason_en": "You could also say it more politely.",
                "grounding_ids": [],
            },
            ensure_ascii=False,
        )
        result = parse_correction(answer)
        assert result.needs_correction is False
        assert result.corrected_sentence is None
        assert result.reason_en is None

    def test_rejects_an_answer_with_no_object(self) -> None:
        with pytest.raises(CorrectionFormatError, match="no JSON object"):
            parse_correction("The sentence is fine.")

    def test_rejects_unparseable_json(self) -> None:
        with pytest.raises(CorrectionFormatError, match="did not parse"):
            parse_correction('{"needs_correction": true,}')

    def test_rejects_a_missing_verdict(self) -> None:
        with pytest.raises(CorrectionFormatError, match="needs_correction"):
            parse_correction('{"corrected_sentence": "おはようございます"}')

    def test_rejects_a_verdict_that_is_not_a_boolean(self) -> None:
        with pytest.raises(CorrectionFormatError, match="needs_correction"):
            parse_correction('{"needs_correction": "yes", "corrected_sentence": "はい"}')

    def test_rejects_a_true_verdict_with_no_correction(self) -> None:
        # A correction the learner cannot read is not a correction.
        answer = '{"needs_correction": true, "corrected_sentence": null, "reason_en": "Wrong."}'
        with pytest.raises(CorrectionFormatError, match="without both"):
            parse_correction(answer)

    def test_grounding_ids_default_to_empty(self) -> None:
        answer = '{"needs_correction": false}'
        assert parse_correction(answer).grounding_ids == ()

    def test_grounding_ids_survive_when_present(self) -> None:
        # Week 1 asks for an empty array; week 2 fills it. The key is carried from
        # the start so that adding it later does not invalidate stored data.
        answer = '{"needs_correction": false, "grounding_ids": ["grammar-003"]}'
        assert parse_correction(answer).grounding_ids == ("grammar-003",)


class TestReasonIsEnglish:
    def test_plain_english_passes(self) -> None:
        assert reason_is_english("The polite form is expected when talking to a manager.")

    def test_english_quoting_japanese_passes(self) -> None:
        # Pointing at a word is how a particle gets explained; it is not a failure.
        assert reason_is_english("「は」 marks the topic, so 「が」 sounds odd here.")

    def test_english_naming_japanese_without_quotes_passes(self) -> None:
        # The metric asks whether the answer came back in English. This one did.
        # Counting it as a language failure reports a model as answering in
        # Japanese when it never did — the day 4 baseline run had nine of these.
        assert reason_is_english(
            "The original sentence uses the masu-stem of the verb (遅れ) to end the "
            "sentence, and a verb stem cannot end a sentence on its own. Add です "
            "to make it a complete polite sentence."
        )

    def test_japanese_fails(self) -> None:
        assert not reason_is_english("「ありがとう」は友達に使う言い方です。")

    def test_mostly_japanese_with_an_english_word_fails(self) -> None:
        assert not reason_is_english("This is 丁寧な言い方ではありません。")

    def test_an_empty_reason_is_not_english(self) -> None:
        assert not reason_is_english("   ")

    def test_the_threshold_is_not_inlined(self) -> None:
        # A threshold that can be tuned in a source file produces README numbers
        # nobody can reproduce (docs/ja/glossary.md §7).
        assert threshold("reason_language", "japanese_ratio_max") == engine._JAPANESE_RATIO_MAX


class TestJapaneseLeftUnquoted:
    def test_quoted_japanese_is_not_flagged(self) -> None:
        assert not japanese_left_unquoted("「は」 marks the topic here.")

    def test_unquoted_japanese_is_flagged_even_when_the_reason_is_english(self) -> None:
        # Recorded next to the correction, never counted against it: the correction
        # prompt asks for 「」 and the baseline prompt does not.
        reason = "The masu-stem of the verb (遅れ) cannot end a sentence on its own."
        assert japanese_left_unquoted(reason)
        assert reason_is_english(reason)


class TestCheck:
    def test_returns_the_correction_on_the_first_attempt(self, fake_model: Any) -> None:
        model = fake_model(VALID_ANSWER)
        result = check("おはようです", "greeting", "beginner")

        assert result.learner_sentence == "おはようです"
        assert result.correction is not None
        assert result.correction.corrected_sentence == "おはようございます"
        assert result.attempts == 1
        assert result.format_compliant
        assert len(model.calls) == 1

    def test_retries_once_when_the_answer_is_broken(self, fake_model: Any) -> None:
        model = fake_model("I think that is fine!", VALID_ANSWER)
        result = check("おはようです", "greeting", "beginner")

        assert result.correction is not None
        assert result.attempts == 2
        # The retry has to say what was wrong, or temperature 0 just repeats itself.
        assert len(model.calls[1]) > len(model.calls[0])

    def test_a_repaired_answer_still_counts_as_a_format_failure(self, fake_model: Any) -> None:
        # Otherwise format_compliance_rate reports a model that never breaks the
        # format, which is the same lie as dropping the broken cases entirely.
        fake_model("not JSON", VALID_ANSWER)
        result = check("おはようです", "greeting", "beginner")

        assert result.correction is not None
        assert result.format_problems == ("invalid_json",)
        assert not result.format_compliant

    def test_gives_up_after_the_retry(self, fake_model: Any) -> None:
        model = fake_model("not JSON", "still not JSON")
        result = check("おはようです", "greeting", "beginner")

        assert result.correction is None
        assert result.attempts == MAX_ATTEMPTS
        assert result.format_problems == ("invalid_json",)
        assert len(model.calls) == MAX_ATTEMPTS

    def test_a_japanese_reason_is_used_but_counted_as_non_compliant(
        self, fake_model: Any
    ) -> None:
        answer = json.dumps(
            {
                "needs_correction": True,
                "corrected_sentence": "おはようございます",
                "reason_en": "朝の挨拶は決まった言い方です。",
                "grounding_ids": [],
            },
            ensure_ascii=False,
        )
        fake_model(answer)
        result = check("おはようです", "greeting", "beginner")

        # The judgement is sound; only the language is wrong, so it is not retried
        # and it does not count against the accuracy metrics.
        assert result.correction is not None
        assert result.attempts == 1
        assert result.format_problems == ("reason_not_english",)

    def test_the_judgement_is_deterministic(self) -> None:
        # The same sentence measured twice has to give the same label, or the
        # evaluation numbers move between runs on their own.
        assert TEMPERATURE == 0.0

    def test_an_unknown_scene_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown scene"):
            check("おはようです", "restaurant", "beginner")
