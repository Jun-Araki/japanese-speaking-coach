"""Tests for checking a whole conversation at once, without calling the model.

`run_correction` is stubbed everywhere here. What is being pinned is the two
properties the review screen depends on and neither of which the graph provides:
that the answers come back in the order the learner spoke, and that one sentence
failing costs exactly one sentence.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from app import corrections as batch
from correction import Correction, CorrectionResult


def answer(sentence: str) -> dict[str, Any]:
    """What the graph returns for one sentence, in the shape the caller unpacks."""
    correction = Correction(
        needs_correction=False,
        corrected_sentence=None,
        reason_en="This one is fine.",
    )
    result = CorrectionResult(sentence, correction=None, attempts=1, format_problems=())
    return {"result": result, "correction": correction}


class TestOrder:
    def test_answers_come_back_in_the_order_they_were_said(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The first sentence is made the slowest one, so a batch that yielded by
        # completion would put it last. The review has to read like the
        # conversation did, or the learner cannot find the line they remember.
        delays = {"いち。": 0.06, "に。": 0.04, "さん。": 0.02, "よん。": 0.0}

        def slow(sentence: str, scene: str, level: str) -> dict[str, Any]:
            time.sleep(delays[sentence])
            return answer(sentence)

        monkeypatch.setattr(batch, "run_correction", slow)

        results = batch.correct_all(list(delays), "shop", "beginner")

        assert [result.learner_sentence for result in results] == list(delays)

    def test_no_sentences_is_no_work(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def never(sentence: str, scene: str, level: str) -> dict[str, Any]:
            raise AssertionError("nothing should be corrected")

        monkeypatch.setattr(batch, "run_correction", never)

        assert batch.correct_all([], "shop", "beginner") == []


class TestFailure:
    def test_one_failure_does_not_take_the_others_with_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def sometimes(sentence: str, scene: str, level: str) -> dict[str, Any]:
            if sentence == "に。":
                raise RuntimeError("429 from the provider")
            return answer(sentence)

        monkeypatch.setattr(batch, "run_correction", sometimes)

        results = batch.correct_all(["いち。", "に。", "さん。"], "shop", "beginner")

        # The failed sentence keeps its place and its text, with nothing attached:
        # the review says it could not be checked rather than pretending it was
        # fine, and "You said 3 sentences" still counts three.
        assert [result.learner_sentence for result in results] == ["いち。", "に。", "さん。"]
        assert results[1].correction is None
        assert [result.correction is not None for result in results] == [True, False, True]


class TestWidth:
    def test_the_ceiling_holds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A ceiling, not a target. It was raised from five to ten on 2026-08-22,
        # after thirty simultaneous corrections were measured succeeding; what is
        # pinned here is that a ceiling still exists, whatever it is set to.
        # Unbounded width invites a 429, and a 429 does not make the corrections
        # slow -- it makes them missing.
        lock = threading.Lock()
        running = 0
        peak = 0

        def counted(sentence: str, scene: str, level: str) -> dict[str, Any]:
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            time.sleep(0.02)
            with lock:
                running -= 1
            return answer(sentence)

        monkeypatch.setattr(batch, "run_correction", counted)

        batch.correct_all([f"{index}。" for index in range(40)], "shop", "beginner")

        assert peak <= batch.MAX_CORRECTION_WORKERS
