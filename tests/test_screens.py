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

from correction import Correction, CorrectionResult

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
