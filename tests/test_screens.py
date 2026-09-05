"""The two sentences that only appear on one screen, under one condition.

WHY THESE ARE TESTED AND THE REST OF THE SCREEN IS NOT. Streamlit code was treated
as untestable in this project — `audio_cache` (2026-08-22) went in with a note saying
so — and that was wrong: `AppTest` runs the script in-process, with session state set
from the outside and no provider anywhere near it. What it cannot do is tell you
whether a page looks right, so nothing here asserts about layout.

WHAT IS WORTH PINNING IS A CONDITION, NOT A STRING. The review's note about
transcription exists because `render_input` removed a confirmation step and promised
this in its place; it was promised on 2026-08-21 and not written until 2026-08-25,
which is exactly the kind of gap a test closes. The other one is a pair: two
different reasons the voice can go silent, and telling a learner the wrong one sends
them looking for the wrong cause.
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from app import continuous
from app import corrections as app_corrections
from correction import Correction, CorrectionResult
from dialogue import LEVELS, SCENES, Utterance

SPOKEN = CorrectionResult(
    "オフィスでいます。",
    Correction(True, "オフィスにいます。", "Use に with いる.", ()),
    1,
    (),
)
FINE = CorrectionResult("おはようございます。", Correction(False, None, None, ()), 1, ())


@pytest.fixture(autouse=True)
def _no_provider_and_no_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key that is never used, and no access code in front of the screen."""
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key-nothing-is-called")
    monkeypatch.delenv("ACCESS_CODE", raising=False)


def _captions(app: AppTest) -> list[str]:
    return [caption.value for caption in app.caption]


def _a_microphone_that_never_arrives(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """A stream that is drawn and never carries a frame. Returns what was asked for."""
    asked: list[bool] = []

    class Silent:
        class state:
            playing = False

        audio_receiver = None

    def open_stream(*, keep_trying: bool = True) -> Silent:
        asked.append(keep_trying)
        return Silent()

    # `collect_turn` IS NOT FAKED. It is the code that writes the caption this class
    # asserts on, and against a stream that is not live it captions and returns —
    # no frames, no browser, no waiting.
    monkeypatch.setenv("CONTINUOUS_VOICE", "1")
    monkeypatch.setattr(continuous, "open_stream", open_stream)
    return asked


def _a_microphone_that_carries_audio(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """A stream that is live. Without one, nothing tests the branch that resets.

    A receiver that raises is a stalled stream, which `collect_turn` is written to
    treat as "no turn" rather than as a crash — so the run ends where a real one
    would, having already recorded that the microphone works.
    """
    asked: list[bool] = []

    class Carrying:
        class state:
            playing = True

        audio_receiver: object

    class Stalled:
        def get_frames(self, timeout: float) -> list[object]:
            # AND IT DROPS AS IT STALLS. A stream that is live and delivers nothing
            # makes the real screen go round again and wait, which in a test is a
            # loop with no way out. Dropping here is the honest end of the same run:
            # the count has already been reset by the live branch above.
            Carrying.state.playing = False
            raise TimeoutError("no frames, which is not a crash")

    Carrying.audio_receiver = Stalled()

    def open_stream(*, keep_trying: bool = True) -> Carrying:
        asked.append(keep_trying)
        return Carrying()

    monkeypatch.setenv("CONTINUOUS_VOICE", "1")
    monkeypatch.setattr(continuous, "open_stream", open_stream)
    return asked


class TestTheReviewSaysWhenTranscriptionMayHaveHelped:
    def test_the_note_is_there_after_a_spoken_conversation(self) -> None:
        app = AppTest.from_file("app/main.py", default_timeout=60)
        app.session_state["review"] = [SPOKEN, FINE]
        app.session_state["review_used_speech"] = True

        app.run()

        assert any("spoken and transcribed" in caption for caption in _captions(app))

    def test_a_typed_conversation_is_not_warned_about_transcription(self) -> None:
        # Nothing repaired a typed sentence on its way in, so the warning would be
        # false — and a "this one is fine" that IS fine would be doubted for nothing.
        app = AppTest.from_file("app/main.py", default_timeout=60)
        app.session_state["review"] = [SPOKEN, FINE]
        app.session_state["review_used_speech"] = False

        app.run()

        assert not any("spoken and transcribed" in caption for caption in _captions(app))


class TestTheStartScreenNamesTheRightSilence:
    def test_the_browser_voice_points_at_the_device(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BROWSER_VOICE", "1")

        app = AppTest.from_file("app/main.py", default_timeout=60).run()

        assert any("no Japanese voice installed" in caption for caption in _captions(app))

    def test_the_provider_voice_points_at_the_shared_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # `BROWSER_VOICE=0` is the lever for a venue whose devices have no Japanese
        # voice. It goes quiet too, for the opposite reason: one free-tier key, one
        # room. The learner is told the reply is written down either way.
        monkeypatch.setenv("BROWSER_VOICE", "0")

        app = AppTest.from_file("app/main.py", default_timeout=60).run()

        assert any("shared by everyone using this demo" in caption for caption in _captions(app))


class TestTheScreenStopsAskingForAMicrophoneThatNeverComes:
    """The count that decides it, tested where it is actually kept.

    The predicate has its own tests next to the widget; what those cannot see is the
    wiring — whether the screen increments anything, whether it hands the answer to
    the component, whether ending the conversation forgets it. Removing
    `keep_trying=` from the call and deleting the counter both left the rest of the
    suite green, which is the definition of an untested seam.
    """

    def _in_a_conversation(self, app: AppTest) -> AppTest:
        app.session_state["scene"] = next(iter(SCENES))
        app.session_state["level"] = next(iter(LEVELS))
        # A learner line, and a partner line after it: nothing is owed a reply, so no
        # provider is reachable from here — and `said` is not empty, so ending the
        # conversation really goes through the correction call.
        app.session_state["history"] = [
            Utterance("partner", "おはようございます。"),
            Utterance("learner", "おはようございます。"),
            Utterance("partner", "いい天気ですね。"),
        ]
        app.session_state["corrections"] = []
        app.session_state["spoken"] = 3
        app.session_state["failure"] = None
        return app

    def test_it_keeps_asking_while_the_stream_is_being_negotiated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked = _a_microphone_that_never_arrives(monkeypatch)
        app = self._in_a_conversation(AppTest.from_file("app/main.py", default_timeout=60))

        for _ in range(continuous.GIVE_UP_AFTER):
            app.run()

        # A successful connection spends two of these runs, so every one of them has
        # to still be asking. This is the assertion that fails if the number is cut.
        assert asked == [True] * continuous.GIVE_UP_AFTER
        assert app.session_state["dead_runs"] == continuous.GIVE_UP_AFTER

    def test_it_stops_asking_once_the_stream_has_never_come_up(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked = _a_microphone_that_never_arrives(monkeypatch)
        app = self._in_a_conversation(AppTest.from_file("app/main.py", default_timeout=60))

        for _ in range(continuous.GIVE_UP_AFTER + 1):
            app.run()

        assert asked[-1] is False
        assert any(
            "did not connect" in caption for caption in _captions(app)
        ), "the screen still says it is starting a microphone it stopped asking for"

    def test_a_working_microphone_is_recorded_and_the_count_goes_back_to_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # THE BRANCH THAT WAS NEVER RUN. Every other test here uses a stream that
        # cannot go live, so deleting either line in the live branch left the whole
        # suite green — and with it the memory that keeps a working microphone.
        _a_microphone_that_carries_audio(monkeypatch)
        app = self._in_a_conversation(AppTest.from_file("app/main.py", default_timeout=60))
        app.session_state["dead_runs"] = 4

        app.run()

        assert app.session_state["dead_runs"] == 0
        assert app.session_state["stream_was_live"] is True

    def test_a_stream_that_carried_audio_is_asked_for_again(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Written the long way round — one live run, then far more dead runs than the
        # threshold — so that the memory is the app's own rather than one this test
        # put in session state for it.
        live = _a_microphone_that_carries_audio(monkeypatch)
        app = self._in_a_conversation(AppTest.from_file("app/main.py", default_timeout=60))
        app.run()
        assert live == [True]

        dead = _a_microphone_that_never_arrives(monkeypatch)
        for _ in range(continuous.GIVE_UP_AFTER * 2):
            app.run()

        assert dead == [True] * (continuous.GIVE_UP_AFTER * 2)
        assert not any("did not connect" in caption for caption in _captions(app))

    def test_the_caption_never_disagrees_with_the_widget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The run where the count crosses the threshold is the one that used to lie:
        # the caption said the microphone had not connected while the widget was
        # still being told to keep asking for it. Checked on every run, because the
        # crossing run is the only one where it showed.
        asked = _a_microphone_that_never_arrives(monkeypatch)
        app = self._in_a_conversation(AppTest.from_file("app/main.py", default_timeout=60))

        for _ in range(continuous.GIVE_UP_AFTER + 2):
            app.run()
            gave_up = any("did not connect" in caption for caption in _captions(app))
            assert gave_up is (asked[-1] is False), (
                f"run {len(asked)}: widget asked={asked[-1]}, caption gave up={gave_up}"
            )

    def test_ending_the_conversation_forgets_the_count(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Otherwise the next conversation starts on a phone whose microphone has
        # already been given up on, for a reason that belonged to the last one.
        monkeypatch.setattr(app_corrections, "correct_all", lambda *a, **k: [])
        _a_microphone_that_carries_audio(monkeypatch)
        app = self._in_a_conversation(AppTest.from_file("app/main.py", default_timeout=60))
        app.run()
        assert app.session_state["stream_was_live"] is True

        ending = [button for button in app.button if "End the conversation" in button.label]
        assert ending, "the conversation screen has no way out"
        ending[0].click().run()

        # BOTH KEYS. The count is the obvious one; the memory of a microphone that
        # worked is the one that would quietly carry a verdict about the last phone
        # into the next conversation.
        assert "dead_runs" not in app.session_state
        assert "stream_was_live" not in app.session_state
