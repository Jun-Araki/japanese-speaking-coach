"""Tests for the speech layer, against recorded answers rather than the provider.

The provider is never called here. What is pinned is the handling around it: the
WAV header without which a browser plays silence and reports nothing, and the
restored full stop without which the correction engine reports a mistake the
learner did not make.
"""

from __future__ import annotations

import base64
import struct
import urllib.error
import urllib.request
from typing import Any

import pytest

from speech import voice


def answer_with_audio(raw: bytes) -> dict[str, Any]:
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "audio/L16;codec=pcm;rate=24000",
                                "data": base64.b64encode(raw).decode(),
                            }
                        }
                    ]
                }
            }
        ]
    }


def answer_with_text(text: str) -> dict[str, Any]:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


class TestClosingASentence:
    def test_adds_a_full_stop_when_there_is_none(self) -> None:
        # Punctuation is not spoken, so its absence is a transcription artefact and
        # not a learner's mistake. Passed on unchanged it becomes a correction for
        # something they did not do.
        assert voice.close_sentence("水をください") == "水をください。"

    def test_leaves_a_sentence_that_already_ends(self) -> None:
        assert voice.close_sentence("はい。") == "はい。"
        assert voice.close_sentence("仕事は何？") == "仕事は何？"
        assert voice.close_sentence("すごい！") == "すごい！"

    def test_leaves_an_empty_transcription_empty(self) -> None:
        # Silence must not become a full stop: an empty string is how the screen
        # knows to ask for another recording.
        assert voice.close_sentence("") == ""


class TestSynthesise:
    def test_wraps_the_raw_samples_in_a_wav_header(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The endpoint returns headerless PCM. A caller that forgot this would get
        # silence with no error — a failure that looks like a broken speaker.
        raw = b"\x00\x01" * 100
        monkeypatch.setattr(voice, "_post", lambda model, payload: answer_with_audio(raw))

        wav = voice.synthesise("おはようございます。")

        assert wav[:4] == b"RIFF"
        assert wav[8:12] == b"WAVE"
        assert wav.endswith(raw)
        # The data chunk has to declare the length that follows it, or players cut
        # the audio short.
        assert struct.unpack("<I", wav[40:44])[0] == len(raw)

    def test_an_answer_with_no_audio_is_an_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(voice, "_post", lambda model, payload: {"candidates": []})

        with pytest.raises(voice.SpeechError, match="no audio"):
            voice.synthesise("おはようございます。")


class TestTranscribe:
    def test_returns_the_sentence_with_its_full_stop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            voice, "_post", lambda model, payload: answer_with_text(" 電車がまだ動きません ")
        )

        assert voice.transcribe(b"RIFF....") == "電車がまだ動きません。"

    def test_silence_comes_back_empty_rather_than_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A learner who pressed record and said nothing has not caused an error.
        monkeypatch.setattr(voice, "_post", lambda model, payload: answer_with_text(""))

        assert voice.transcribe(b"RIFF....") == ""

    def test_no_audio_at_all_never_reaches_the_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def explode(model: str, payload: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("the provider was called for an empty recording")

        monkeypatch.setattr(voice, "_post", explode)

        assert voice.transcribe(b"") == ""

    def test_an_oversized_recording_is_refused_before_the_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def explode(model: str, payload: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("the provider was called with an oversized recording")

        monkeypatch.setattr(voice, "_post", explode)

        with pytest.raises(voice.SpeechError, match="limit"):
            voice.transcribe(b"x" * (voice.MAX_AUDIO_BYTES + 1))

    def test_transcription_is_not_sampled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The learner said one specific thing. Sampling would return different
        # sentences for the same recording, and "say it again" is a button on this
        # screen that would then mean something it does not.
        seen: dict[str, Any] = {}

        def capture(model: str, payload: dict[str, Any]) -> dict[str, Any]:
            seen.update(payload)
            return answer_with_text("はい。")

        monkeypatch.setattr(voice, "_post", capture)
        voice.transcribe(b"RIFF....")

        assert seen["generationConfig"]["temperature"] == 0


class TestProviderErrorsDoNotEscape:
    """A failure to read one line aloud must not end the conversation.

    On 2026-08-21 a 4xx from the synthesis endpoint came out of this module as
    `urllib.error.HTTPError`, went past a caller catching `SpeechError`, and took the
    whole deployed page down mid-conversation. Callers can only handle the error type
    this module documents, so this is where the conversion has to happen.
    """

    def test_an_http_error_becomes_a_speech_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(request: object, timeout: float) -> object:
            raise urllib.error.HTTPError(
                "https://example.test", 429, "Too Many Requests", {}, None  # type: ignore[arg-type]
            )

        monkeypatch.setattr(urllib.request, "urlopen", refuse)

        with pytest.raises(voice.SpeechError, match="429"):
            voice.synthesise("おはようございます。")

    def test_a_network_failure_becomes_a_speech_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def unreachable(request: object, timeout: float) -> object:
            raise TimeoutError("timed out")

        monkeypatch.setattr(urllib.request, "urlopen", unreachable)

        with pytest.raises(voice.SpeechError, match="could not be reached"):
            voice.transcribe(b"RIFF....")
