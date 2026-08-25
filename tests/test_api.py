"""Tests for the HTTP layer and the graph under it.

No provider is called and no index is built: the graph's nodes are replaced with
recorded answers, which is the same rule the correction tests follow.

The test that matters most is the one pinning the graph to the engine every
published number was measured through. It compares against `engine.judge` with the
same articles, which is what `check_with_retrieval` calls once its search returns —
the search itself is stubbed on both sides, so what is compared is everything after
it. The graph is what ships, so if the two ever disagree, the README describes an
engine that is not the one running.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from correction import engine
from correction.engine import Correction
from graph import correction_graph

RECORDED = Correction(
    needs_correction=True,
    corrected_sentence="スーパーで買い物します。",
    reason_en="Use 「で」 for where an action happens.",
    grounding_ids=("grammar-001",),
)


class _FakeModel:
    def __init__(self, correction: Correction) -> None:
        self._correction = correction

    def invoke(self, messages: object) -> object:
        payload = {
            "needs_correction": self._correction.needs_correction,
            "corrected_sentence": self._correction.corrected_sentence,
            "reason_en": self._correction.reason_en,
            "grounding_ids": list(self._correction.grounding_ids),
        }
        return type("Answer", (), {"content": json.dumps(payload, ensure_ascii=False)})()


class _Section:
    """Shaped like a retrieval Result, without importing one."""

    def __init__(self, article_id: str) -> None:
        self.article_id = article_id
        self.heading = "で — where an action happens"
        self.body = "公園で写真を撮りました。"


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No provider, no embeddings — recorded answers in both nodes."""
    monkeypatch.setattr(engine, "build_chat_model", lambda temperature: _FakeModel(RECORDED))
    monkeypatch.setattr(
        correction_graph,
        "retrieve",
        lambda state: {"articles": "[grammar-001] ...", "allowed_ids": {"grammar-001"}},
    )
    # The compiled graph holds the node functions it was built with, so it has to be
    # rebuilt after they are replaced.
    monkeypatch.setattr(correction_graph, "_GRAPH", None)


class TestTheGraphAndTheEngineAgree:
    def test_same_answer_from_both_paths(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The engine's own retrieval is stubbed at the search level so the two paths
        # see identical articles; what is being compared is everything after that.
        monkeypatch.setattr(engine, "build_chat_model", lambda temperature: _FakeModel(RECORDED))
        sections = [_Section("grammar-001")]
        monkeypatch.setattr(
            correction_graph,
            "retrieve",
            lambda state: dict(
                zip(
                    ("articles", "allowed_ids"),
                    engine.grounding_from(sections),
                    strict=True,
                )
            ),
        )
        monkeypatch.setattr(correction_graph, "_GRAPH", None)

        direct = engine.judge(
            "スーパーに買い物します。", "greeting", "beginner", engine.grounding_from(sections)
        )
        through_graph = correction_graph.run("スーパーに買い物します。", "greeting", "beginner")

        assert through_graph["correction"] == direct.correction

    def test_an_invented_id_does_not_survive_the_graph(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        invented = Correction(
            needs_correction=True,
            corrected_sentence="スーパーで買い物します。",
            reason_en="Use 「で」 for where an action happens.",
            grounding_ids=("grammar-001", "grammar-999"),
        )
        monkeypatch.setattr(engine, "build_chat_model", lambda temperature: _FakeModel(invented))
        monkeypatch.setattr(
            correction_graph,
            "retrieve",
            lambda state: {"articles": "...", "allowed_ids": {"grammar-001"}},
        )
        monkeypatch.setattr(correction_graph, "_GRAPH", None)

        state = correction_graph.run("スーパーに買い物します。", "greeting", "beginner")

        assert state["correction"] is not None
        assert state["correction"].grounding_ids == ("grammar-001",)

    def test_retrieval_failure_still_corrects(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A build without torch must judge sentences, ungrounded. The node catches
        # its own failure rather than letting it end the run.
        # `None` in sys.modules makes the import inside the node raise ImportError,
        # which is what a build without torch actually does.
        monkeypatch.setitem(__import__("sys").modules, "retrieval.index", None)
        state = correction_graph.retrieve({"sentence": "はい。", "scene": "greeting"})

        assert state == {"articles": "", "allowed_ids": set()}


class TestCheckEndpoint:
    def test_returns_the_correction_and_its_citations(self, offline: None) -> None:
        client = TestClient(app)

        response = client.post(
            "/check",
            json={"sentence": "スーパーに買い物します。", "scene": "greeting", "level": "beginner"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["needs_correction"] is True
        assert body["corrected_sentence"] == "スーパーで買い物します。"
        assert body["grounding_ids"] == ["grammar-001"]
        assert body["discarded"] is None

    def test_a_discarded_correction_is_reported_not_hidden(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Check 1 turns a far rewrite into "nothing to correct". The learner sees
        # nothing either way, so the thrown-away sentence has to be visible from
        # outside or a bad check can only be found in a run record.
        replaced = Correction(
            needs_correction=True,
            corrected_sentence="本日は大変よいお天気でございますね。まったくその通りです。",
            reason_en="A different sentence entirely.",
            grounding_ids=(),
        )
        monkeypatch.setattr(engine, "build_chat_model", lambda temperature: _FakeModel(replaced))
        monkeypatch.setattr(
            correction_graph, "retrieve", lambda state: {"articles": "", "allowed_ids": set()}
        )
        monkeypatch.setattr(correction_graph, "_GRAPH", None)

        body = TestClient(app).post(
            "/check",
            json={"sentence": "はい。", "scene": "greeting", "level": "beginner"},
        ).json()

        assert body["needs_correction"] is False
        assert body["validation_reason"] == "rewrite_too_far"
        assert body["discarded"].startswith("本日は")


class TestChatEndpoint:
    def test_an_empty_history_gets_the_opening_line(self) -> None:
        # No model is called for this one: the opening line is fixed per scene, so
        # the conversation starts the same way every time it is measured.
        body = TestClient(app).post(
            "/chat", json={"scene": "greeting", "level": "beginner", "history": []}
        ).json()

        assert body["reply"]

    def test_an_unknown_speaker_is_rejected_at_the_edge(self) -> None:
        response = TestClient(app).post(
            "/chat",
            json={
                "scene": "greeting",
                "level": "beginner",
                "history": [{"speaker": "narrator", "text": "..."}],
            },
        )

        assert response.status_code == 422


class TestHealth:
    def test_says_what_the_build_can_do(self) -> None:
        body = TestClient(app).get("/health").json()

        assert body["status"] == "ok"
        assert body["stores_anything"] is False
        # Reported either way. A health check that says "ok" while grounding is
        # silently gone would hide the failure that matters most on the free tier.
        assert "available" in body["retrieval"]
        assert body["scenes"]
