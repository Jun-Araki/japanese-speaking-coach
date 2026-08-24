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
import urllib.error
import urllib.request
from array import array
from typing import Any, Final

# Preview, and named here so a run record or a bug report can say which one spoke.
DEFAULT_TTS_MODEL: Final = "gemini-2.5-flash-preview-tts"
DEFAULT_TTS_VOICE: Final = "Kore"

# Transcription rides on a text model that takes audio inline, and since 2026-08-24
# it is the LITE one — which is both faster and, far more importantly, worse at
# repairing the learner. Measured on the same five clips both ways:
#
#   gemini-2.5-flash          3.14s   「オフィスでいます」→「オフィスにいます」
#   gemini-flash-lite-latest  1.90s   「オフィスでいます」→「オフィスでいます」
#
# The bigger model writes down what the speaker MEANT. That is excellent
# transcription and, for an app whose whole function is telling a learner what they
# got wrong, it is the erasure of the thing being practised —
# docs/ja/architecture.md has carried that measurement, and this weakness, since
# 2026-08-20. The lite model is less fluent and therefore more faithful: it kept the
# wrong particle in two of the five and the dropped verb in a third.
#
# It costs a habit of putting spaces between words, which Japanese does not use and
# `strip_spacing` below removes — in this layer, for the same reason the full stop is
# restored in this layer.
#
# The text model of this family 404s on this key; only the audio path works. That is
# why the conversation still runs on gemini-2.5-flash.
DEFAULT_TRANSCRIBE_MODEL: Final = "gemini-flash-lite-latest"

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
    """Raised when audio could not be transcribed or synthesised.

    Carries the HTTP status when there was one, because callers need to tell the
    kinds apart: 429 means "stop asking for a while and everyone gets some", and a
    400 means this build is wrong. Sniffing the number out of the message string
    would work until someone reworded the message.
    """

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise SpeechError("GEMINI_API_KEY is not set. It is read from the environment.")
    return key


def _post(model: str, payload: dict[str, Any]) -> dict[str, Any]:
    """One call, with every network failure arriving as SpeechError.

    THE PROVIDER'S EXCEPTIONS MUST NOT ESCAPE THIS MODULE. On 2026-08-21 a 4xx from
    the synthesis endpoint came out of here as `urllib.error.HTTPError`, went past a
    caller that was catching `SpeechError`, and took the whole page down mid
    conversation — a failure to read one line aloud ended the session. Callers can
    only be expected to handle the error type this module documents.
    """
    request = urllib.request.Request(
        _ENDPOINT.format(model=model),
        data=json.dumps(payload).encode(),
        headers={"x-goog-api-key": _key(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            result: dict[str, Any] = json.load(response)
    except urllib.error.HTTPError as exc:
        # THE STATUS IS NOT ENOUGH, AND 2026-08-22 IS WHY. A 400 reached the screen
        # as "answered 400 Bad Request" and nothing else, which is a sentence with no
        # next step in it: the provider puts the actual complaint in the response
        # body, and this clause used to drop the body on the floor. On 13 September
        # that one line of log is all anyone will have.
        raise SpeechError(
            f"{model} answered {exc.code} {exc.reason}: {_why(exc)}", status=exc.code
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SpeechError(f"{model} could not be reached: {exc}") from exc
    return result


def _why(exc: urllib.error.HTTPError) -> str:
    """The provider's own explanation, out of the error body.

    Trimmed, because this ends up on a single stderr line that whoever is running the
    demo has to take in at a glance. Anything unreadable comes back as a plain note
    rather than as a second failure: a body that cannot be parsed must not replace the
    status that could be.
    """
    try:
        body = exc.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - the body is a bonus, never a requirement
        return "no details in the response"
    try:
        message = str(json.loads(body)["error"]["message"])
    except (json.JSONDecodeError, KeyError, TypeError):
        message = body.strip() or "no details in the response"
    return message[:200]


def wav_header(sample_count: int, rate: int = _PCM_RATE) -> bytes:
    """A RIFF header for raw PCM.

    The rate is a parameter because two callers need different ones: synthesis comes
    back at 24kHz, and the microphone is resampled to 16kHz before it is sent. A
    header that lies about the rate plays at the wrong speed and transcribes as
    gibberish, with nothing on screen suggesting why.
    """
    byte_rate = rate * _PCM_CHANNELS * _PCM_BITS // 8
    block_align = _PCM_CHANNELS * _PCM_BITS // 8
    return (
        b"RIFF"
        + struct.pack("<I", 36 + sample_count)
        + b"WAVEfmt "
        + struct.pack(
            "<IHHIIHH", 16, 1, _PCM_CHANNELS, rate, byte_rate, block_align, _PCM_BITS
        )
        + b"data"
        + struct.pack("<I", sample_count)
    )


# Below this peak there is nothing in the recording worth sending. Speech peaks well
# above it even from a quiet speaker held at arm's length; a silent room, a muted
# microphone and a stream that carried nothing all sit under it.
SILENT_PEAK: Final = 0.02


def loudest_sample(wav: bytes) -> float:
    """The peak of a 16-bit WAV, as a fraction of full scale. Zero if unreadable.

    PEAK, NOT RMS, and deliberately not the same question the turn detector asks.
    That one decides whether the room is quiet RIGHT NOW, where a single click must
    not read as speech, so it averages. This one asks whether the whole recording
    contains anything at all, and for that the loudest moment is the answer: a five
    second clip holding one short sentence has a low average and is not silent.
    """
    if len(wav) < 46 or wav[:4] != b"RIFF":
        return 0.0
    usable = (len(wav) - 44) // 2 * 2
    pcm = array("h", wav[44 : 44 + usable])
    if not pcm:
        return 0.0
    return max(abs(value) for value in pcm) / 32768


def playback_seconds(wav: bytes) -> float:
    """How long a WAV takes to play, read out of its own header.

    The continuous listener needs this. The reply is handed to the browser to play
    and the microphone starts collecting in the same breath, so the collector has to
    know how long the app will be talking in order to throw those frames away rather
    than transcribe its own voice. Bytes are the only thing available at that point:
    nothing here plays the audio, so nothing here is told when it finished.

    Anything that is not a WAV this module produced is reported as zero, which turns
    the discard off rather than guessing a length — an over-long guess would eat the
    beginning of the learner's sentence.
    """
    if len(wav) < 44 or wav[:4] != b"RIFF":
        return 0.0
    byte_rate: int = struct.unpack("<I", wav[28:32])[0]
    declared: int = struct.unpack("<I", wav[40:44])[0]
    if byte_rate <= 0:
        return 0.0
    # The smaller of what the header claims and what actually arrived: a truncated
    # download would otherwise be reported at its intended length.
    return min(declared, len(wav) - 44) / byte_rate


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
    chosen = model or os.environ.get("TRANSCRIBE_MODEL", DEFAULT_TRANSCRIBE_MODEL)

    # ONE RETRY, THE SAME ONE `synthesise` HAS, and for the same measured reason: this
    # provider sometimes answers with a candidate carrying no content at all. Without
    # it, that fault reached the learner as "Nothing was heard. Please try again." —
    # the app telling someone who had just spoken a sentence that they had not.
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        answer = _post(chosen, payload)
        try:
            parts = answer["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError) as exc:
            if attempt == _MAX_ATTEMPTS:
                # NOT THE SAME AS SILENCE, and the caller has to be able to tell.
                # Silence does not come back empty from this model — asked for a
                # transcription of two seconds of nothing on 2026-08-24 it answered
                # 「はい」 — so an empty answer here is the provider failing, not the
                # learner staying quiet.
                raise SpeechError(
                    f"{chosen} answered with no transcription in it "
                    f"(finish reason: {_finish_reason(answer)})"
                ) from exc
            continue
        said = "".join(part.get("text", "") for part in parts).strip()
        return close_sentence(strip_spacing(said))

    raise AssertionError("the loop above always returns or raises")


def _finish_reason(answer: dict[str, Any]) -> str:
    """Why the model stopped, when it stopped without saying anything."""
    try:
        return str(answer["candidates"][0].get("finishReason", "not given"))
    except (KeyError, IndexError, TypeError):
        return str(answer.get("promptFeedback", {}).get("blockReason", "no candidates"))


def strip_spacing(text: str) -> str:
    """Take out the spaces a transcriber put between Japanese words.

    JAPANESE DOES NOT WRITE THEM, so a learner never typed one and never said one.
    The lite model returns 「スーパー に 買い物 し ます 。」 for a sentence spoken without
    a pause anywhere in it — a tokeniser's habit showing through, not something about
    the speech.

    Left alone it reaches the correction engine, which would be judging a sentence
    nobody wrote. Fixed here rather than in the correction prompt for the same reason
    the full stop is: that prompt is the one every published number was measured on.

    Spaces between ASCII words are kept. A learner saying a foreign name or a number
    can legitimately produce one.
    """
    out: list[str] = []
    for index, char in enumerate(text):
        if char == " " and 0 < index < len(text) - 1:
            before, after = text[index - 1], text[index + 1]
            if not (before.isascii() and before.isalnum()) or not (
                after.isascii() and after.isalnum()
            ):
                continue
        out.append(char)
    return "".join(out).strip()


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
