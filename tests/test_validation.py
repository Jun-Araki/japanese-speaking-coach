"""Tests for the deterministic checks run over a correction.

The thresholds themselves are measurements and live in config/thresholds.toml.
What is pinned here is the behaviour that depends on them: which sentences survive,
what a discarded correction turns into, and that the discarded one is still
readable afterwards. The last matters most — when the real implementation scores
worse than the baseline, the first suspect is this file throwing away corrections
that were fine, and that question can only be answered from what it kept.
"""

from __future__ import annotations

from config import threshold
from correction.engine import Correction
from correction.validation import edit_distance, rewritten_too_far, validate

# An answer that kept nothing of the sentence and is far longer. After the 8/11
# measurement the threshold sits above every distance the baseline actually
# produced, so this is what is left for the check to catch.
REPLACED = "本日は大変よいお天気でございますね。まったくその通りです。"


def correction(corrected: str | None = "おはようございます", needs: bool = True) -> Correction:
    return Correction(
        needs_correction=needs,
        corrected_sentence=corrected,
        reason_en="A fixed phrase." if needs else None,
    )


class TestEditDistance:
    def test_counts_insertions_deletions_and_substitutions(self) -> None:
        assert edit_distance("ありがとう", "ありがとう") == 0
        assert edit_distance("ありがとう", "ありがとうございます") == 5
        assert edit_distance("行くです", "行きます") == 2


class TestRewrittenTooFar:
    def test_keeps_the_most_common_correction_this_app_makes(self) -> None:
        # ありがとう -> ありがとうございます is a normalised 0.50, and it is both the
        # commonest correction here and the most obviously right one. A threshold
        # of 0.5 — the obvious first choice — would discard it silently, and a
        # discarded correction reaches neither the learner nor the metrics.
        assert not rewritten_too_far("ありがとう", "ありがとうございます")
        assert not rewritten_too_far("おはようです", "おはようございます")

    def test_discards_an_answer_that_replaced_the_sentence(self) -> None:
        # Above the whole observed range: measured over 73 real corrections the
        # largest was 0.82, and that one was correct. What is left for this check
        # is the pathological case — an answer that shares almost nothing with the
        # sentence and is far longer.
        assert rewritten_too_far("はい。", REPLACED)

    def test_short_sentences_are_judged_by_absolute_distance(self) -> None:
        # One character out of four is 0.25 of a sentence and means almost nothing,
        # so below `short_sentence_chars` the ratio is not used at all.
        assert not rewritten_too_far("行くです", "行きます")

    def test_the_thresholds_are_not_inlined(self) -> None:
        assert threshold("rewrite_too_far", "normalised_distance_max") == 0.85
        assert threshold("rewrite_too_far", "short_sentence_chars") == 8


class TestValidate:
    def test_leaves_a_reasonable_correction_alone(self) -> None:
        result = validate("おはようです", correction())

        assert result.correction.needs_correction is True
        assert result.fired is False
        assert result.discarded is None

    def test_a_discarded_correction_comes_back_as_no_correction_needed(self) -> None:
        # Not left as `true` with nothing attached: the learner sees nothing either
        # way, but that state would still be counted as a detection and is one
        # `parse_correction` refuses to build.
        result = validate("はい。", correction(REPLACED))

        assert result.correction.needs_correction is False
        assert result.correction.corrected_sentence is None
        assert result.correction.reason_en is None

    def test_what_was_thrown_away_is_still_readable(self) -> None:
        # The whole point. A node that cannot show its rejections cannot be
        # debugged when the implementation scores below the baseline.
        result = validate("はい。", correction(REPLACED))

        assert result.fired is True
        assert result.reason == "rewrite_too_far"
        assert result.discarded is not None
        assert result.discarded.corrected_sentence == REPLACED

    def test_does_nothing_when_there_was_no_correction_to_check(self) -> None:
        result = validate("今日は暑いね。", correction(corrected=None, needs=False))

        assert result.correction.needs_correction is False
        assert result.fired is False
