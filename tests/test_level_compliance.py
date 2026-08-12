"""Tests for the level-compliance measurement.

One property matters more than the rest: the headline figure has to be the reply
the model produced, not the reply the gate produced. The two differ only when the
gate fires, and when they were confused the number went UP — which is the failure
mode nobody investigates.

That is not hypothetical. This script called `reply()`, the gate landed inside
`reply()` a commit later, and for one commit the "first-shot" figure was measuring
post-regeneration replies. Caught by reading, not by a test. Hence this file.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any

from evals.level_compliance import measure, run_record

reply_module = importlib.import_module("dialogue.reply")

# Above beginner level: 弊社, 懸案, 鋭意 are all far over. Used as the first answer
# so the gate has something to reject.
HARD = "弊社の懸案事項を鋭意検討します。"
EASY = "はい、そうします。"


def scripted(monkeypatch: Any, *answers: str) -> None:
    """Replace the provider with one that cycles through these answers.

    Cycling rather than draining: the measurement makes 30 calls per level and each
    reply may cost two, so a list that runs out would end the run instead of
    scripting it. With (HARD, EASY) every first attempt is over level and every
    retry is not, which is the case the first-shot figure exists to separate.

    The first version returned the last answer forever once the list was down to
    one, so only turn 1 was ever hard and the test asserted 0% against a run that
    was 96.7% compliant. A fake that cannot produce the situation under test is
    worse than no test.
    """
    replies = list(answers)

    class ScriptedModel:
        calls = 0

        def invoke(self, messages: list[Any]) -> Any:
            answer = replies[ScriptedModel.calls % len(replies)]
            ScriptedModel.calls += 1
            return SimpleNamespace(content=answer)

    monkeypatch.setattr(reply_module, "build_chat_model", lambda temperature: ScriptedModel())


class TestFirstShotIsTheUngatedReply:
    def test_a_rescued_reply_counts_as_a_first_shot_failure(self, monkeypatch: Any) -> None:
        # Every reply starts over level and is rescued by the retry. The learner
        # sees a compliant conversation; the model did not produce one.
        scripted(monkeypatch, HARD, EASY)

        outcomes = measure(("beginner",))
        record = run_record(outcomes, "20260812-0000")

        assert record["after_regeneration_rate"] == 1.0
        assert record["first_shot_rate"] == 0.0
        assert record["regenerations"] == len(outcomes)

    def test_the_two_agree_when_the_gate_never_fires(self, monkeypatch: Any) -> None:
        scripted(monkeypatch, EASY)

        record = run_record(measure(("beginner",)), "20260812-0000")

        assert record["first_shot_rate"] == 1.0
        assert record["after_regeneration_rate"] == 1.0
        assert record["regenerations"] == 0

    def test_the_discarded_first_attempt_is_kept_per_item(self, monkeypatch: Any) -> None:
        # Without it the record cannot say what was rejected, and a compliance rate
        # of 100% after regeneration is unreadable.
        scripted(monkeypatch, HARD, EASY)

        record = run_record(measure(("beginner",)), "20260812-0000")

        assert record["results"][0]["first_shot"] == HARD
        assert record["results"][0]["reply"] == EASY
        assert record["results"][0]["first_shot_passes"] is False

    def test_the_record_says_regeneration_was_in_force(self, monkeypatch: Any) -> None:
        # A record taken before the gate existed and one taken after are different
        # measurements, and the date is not enough to tell them apart.
        scripted(monkeypatch, EASY)

        record = run_record(measure(("beginner",)), "20260812-0000")

        assert record["regenerated"] is True
        assert record["max_regenerations"] >= 1
