"""Speech in and speech out, through the provider whose key this project has.

THE PLAN SAID OPENAI. IT IS GEMINI, FOR THE REASON THE MODEL CHOICE WAS ALREADY
GEMINI. The planning document names OpenAI's transcription and speech endpoints
(§2-6), and `OPENAI_API_KEY` is empty — the same wall the Anthropic billing form
put up on 2026-08-03, answered the same way: use the key that exists and keep the
swap cheap. Both directions were verified against the real API before this file was
written; a synthesised sentence fed straight back to transcription came out
character for character.

WHAT THAT COSTS, STATED RATHER THAN GLOSSED. The synthesis model is a preview
model, so it can change or disappear with no notice, and this project has no
contract that says otherwise. The fallback is the one already written into the
plan: the partner's reply stays on screen as text, the learner still speaks, and
the core of "practise by talking" survives. Nothing else in the repository depends
on this file.

NOTHING IS KEPT. Audio arrives as bytes, goes to the provider, and the bytes are
dropped when the request ends. A learner's voice is personal data in a way their
typing is not, and the decision not to store anything (§2-5) is easiest to keep by
never having a path that could.

DISCLOSURE IS NOT OPTIONAL. Every speech provider's terms require telling people
the voice is synthetic, and `app.theme.VOICE_NOTICE` is that sentence. It is shown
wherever audio plays.
"""

from __future__ import annotations

import base64
import json
import os
import struct
import urllib.request
from typing import Any, Final

# Preview, and named here so a run record or a bug report can say which one spoke.
DEFAULT_TTS_MODEL: Final = "gemini-2.5-flash-preview-tts"
DEFAULT_TTS_VOICE: Final = "Kore"

# Transcription rides on the ordinary text model, which takes audio inline. Using
# the same model as the conversation keeps one provider and one key.
DEFAULT_TRANSCRIBE_MODEL: Final = "gemini-2.5-flash"

_ENDPOINT: Final = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_TIMEOUT: Final = 60.0

# What the synthesis endpoint returns: signed 16-bit PCM, mono, 24 kHz. It is raw
# samples with no container, so a WAV header has to be put in front of it before a
# browser will play it.
_PCM_RATE: Final = 24_000
_PCM_BITS: Final = 16
_PCM_CHANNELS: Final = 1

# Kept short on purpose. A beginner speaks a sentence, not a paragraph, and a long
# recording is both a bigger bill and a worse transcription.
MAX_AUDIO_BYTES: Final = 8 * 1024 * 1024

_MAX_ATTEMPTS: Final = 2

TRANSCRIBE_PROMPT: Final = (
    "Transcribe the Japanese speech in this audio exactly as spoken. Output only "
    "the transcription — no commentary, no romanisation, no translation. If there "
    "is no speech, output nothing at all."
)


class SpeechError(RuntimeError):
    """Raised when audio could not be transcribed or synthesised."""


def _key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise SpeechError("GEMINI_API_KEY is not set. It is read from the environment.")
    return key


def _post(model: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        _ENDPOINT.format(model=model),
        data=json.dumps(payload).encode(),
        headers={"x-goog-api-key": _key(), "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
        result: dict[str, Any] = json.load(response)
    return result


def wav_header(sample_count: int) -> bytes:
    """A RIFF header for the raw PCM the synthesis endpoint returns."""
    byte_rate = _PCM_RATE * _PCM_CHANNELS * _PCM_BITS // 8
    block_align = _PCM_CHANNELS * _PCM_BITS // 8
    return (
        b"RIFF"
        + struct.pack("<I", 36 + sample_count)
        + b"WAVEfmt "
        + struct.pack(
            "<IHHIIHH", 16, 1, _PCM_CHANNELS, _PCM_RATE, byte_rate, block_align, _PCM_BITS
        )
        + b"data"
        + struct.pack("<I", sample_count)
    )


def synthesise(text: str, model: str | None = None, voice: str | None = None) -> bytes:
    """Read one line aloud. Returns WAV bytes, ready for a browser.

    The header is added here rather than by the caller: the endpoint returns raw
    samples, and a caller that forgot would get silence with no error — the kind of
    failure that looks like a broken speaker rather than a broken call.
    """
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice or os.environ.get("TTS_VOICE", DEFAULT_TTS_VOICE)
                    }
                }
            },
        },
    }
    chosen = model or os.environ.get("TTS_MODEL", DEFAULT_TTS_MODEL)

    # ONE RETRY, for the same reason the correction engine has one: the endpoint
    # occasionally answers with a candidate carrying no content at all — seen twice
    # on 2026-08-20, both times succeeding immediately afterwards on the same input.
    # More than one retry would hide a model that cannot do this at all.
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        answer = _post(chosen, payload)
        try:
            inline = answer["candidates"][0]["content"]["parts"][0]["inlineData"]
        except (KeyError, IndexError) as exc:
            if attempt == _MAX_ATTEMPTS:
                raise SpeechError(f"the synthesis answer had no audio in it: {exc}") from exc
            continue
        raw = base64.b64decode(inline["data"])
        return wav_header(len(raw)) + raw

    raise AssertionError("the loop above always returns or raises")


def transcribe(audio: bytes, mime_type: str = "audio/wav", model: str | None = None) -> str:
    """Turn a recording into the sentence the learner said.

    Returns an empty string when there was no speech, rather than raising: a
    learner who pressed record and said nothing has not caused an error, and the
    screen should ask them to try again rather than show them a failure.
    """
    if not audio:
        return ""
    if len(audio) > MAX_AUDIO_BYTES:
        raise SpeechError(
            f"that recording is {len(audio) // 1024}KB, over the {MAX_AUDIO_BYTES // 1024}KB limit"
        )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": TRANSCRIBE_PROMPT},
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": base64.b64encode(audio).decode(),
                        }
                    },
                ]
            }
        ],
        # The learner said one specific thing. Sampling would make the same
        # recording come back as different sentences on different tries, and
        # "press it again" is a button this screen actually has.
        "generationConfig": {"temperature": 0},
    }
    answer = _post(
        model or os.environ.get("TRANSCRIBE_MODEL", DEFAULT_TRANSCRIBE_MODEL), payload
    )
    try:
        parts = answer["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError):
        return ""
    return close_sentence("".join(part.get("text", "") for part in parts).strip())


# Sentence-final punctuation, in the forms the transcription actually returns.
_CLOSERS: Final = ("。", "？", "！", "?", "!", "、")


def close_sentence(text: str) -> str:
    """Put a full stop on a transcription that has none.

    PUNCTUATION IS NOT SPOKEN, so its absence is not a learner's mistake. Measured
    on 2026-08-20 by synthesising five sentences and transcribing them back: four
    of the five came back correct except for a missing 「。」. Passed on as they
    were, the correction engine would report a mistake the learner did not make —
    and the app would look wrong in the one place a beginner cannot tell whether it
    is wrong.

    Confined to this layer on purpose. Fixing it in the correction prompt would
    change the prompt the published numbers were measured on, to repair something
    that only happens to speech.
    """
    if not text or text.endswith(_CLOSERS):
        return text
    return text + "。"
