"""Tests for collecting one spoken turn, against a fake queue rather than a microphone.

There is no browser here and no WebRTC connection. What is faked is the receiver, and
it is faked the way the real one behaves rather than the way it is convenient to
imagine: `streamlit_webrtc` hands over a bounded FIFO of the last few seconds of
sound, returning THE WHOLE BACKLOG in one call and blocking for a single frame once
there is none. The first version of this file modelled it as a live tap, and passed
while the code under it discarded the wrong seconds entirely.

What is pinned is that neither the seconds recorded before the turn began nor the
seconds in which the app is talking reach the turn detector.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from app import continuous
from speech.voice import playback_seconds

FRAME = 0.02  # 20ms, the size WebRTC delivers
RATE = continuous.TARGET_RATE

# Three distinguishable levels, so a recording can be asked WHICH sound got in.
QUIET = 0.001
SPEECH = 0.2  # the learner answering
ECHO = 0.5  # the app's own voice coming back through the microphone
BACKLOG = 0.9  # what was recorded while the script was busy, before this turn


class FakeFrame:
    """One frame of constant loudness. RMS of a constant array is the constant."""

    def __init__(self, level: float) -> None:
        self._array = np.full(int(RATE * FRAME), level, dtype=np.float32)
        self.sample_rate = RATE

    def to_ndarray(self) -> np.ndarray:
        return self._array


class FakeReceiver:
    """The real receiver's two behaviours: dump the backlog, then trickle."""

    def __init__(self, backlog: list[FakeFrame], live: list[FakeFrame]) -> None:
        self._backlog = list(backlog)
        self._live = list(live)

    def get_frames(self, timeout: float) -> list[FakeFrame]:
        if self._backlog:
            everything, self._backlog = self._backlog, []
            return everything
        if not self._live:
            raise RuntimeError("the stream stalled")
        return [self._live.pop(0)]


class BurstReceiver:
    """A receiver that never returns a batch of one, so the drain never sees its
    own stop condition. Two frames a call is what a script slow enough to let the
    queue refill between reads would see."""

    def __init__(self, supply: list[FakeFrame], per_call: int = 2) -> None:
        self._supply = list(supply)
        self._per_call = per_call

    def get_frames(self, timeout: float) -> list[FakeFrame]:
        if not self._supply:
            raise RuntimeError("the stream stalled")
        batch, self._supply = self._supply[: self._per_call], self._supply[self._per_call :]
        return batch


class FakeState:
    def __init__(self, playing: bool) -> None:
        self.playing = playing


class FakeContext:
    def __init__(
        self,
        live: list[FakeFrame],
        backlog: list[FakeFrame] | None = None,
        playing: bool = True,
    ) -> None:
        self.state = FakeState(playing)
        self.audio_receiver = FakeReceiver(backlog or [], live) if playing else None


class FakeStatus:
    def __init__(self) -> None:
        self.captions: list[str] = []

    def caption(self, text: str) -> None:
        self.captions.append(text)


def frames(*runs: tuple[float, float]) -> list[FakeFrame]:
    """Frames for a series of (seconds, loudness) runs."""
    made: list[FakeFrame] = []
    for seconds, level in runs:
        made.extend(FakeFrame(level) for _ in range(int(round(seconds / FRAME))))
    return made


# What the microphone holds when collecting starts: several seconds recorded while
# the script was transcribing, replying and synthesising.
STALE = frames((3.0, BACKLOG))

# What arrives afterwards: the app reading the reply aloud, then half a second for
# the detector to measure the room, the learner's sentence, and the silence that ends
# the turn.
ECHO_THEN_TURN: tuple[tuple[float, float], ...] = (
    (1.0, ECHO),
    (0.5, QUIET),
    (1.0, SPEECH),
    (1.2, QUIET),
)


def seconds_of(audio: bytes | None) -> float:
    assert audio is not None
    return playback_seconds(audio)


def loudest(audio: bytes | None) -> float:
    """The peak sample of a returned recording, as a fraction of full scale."""
    assert audio is not None
    samples = np.frombuffer(audio[44:], dtype="<i2").astype(np.float32) / 32768.0
    return float(np.max(np.abs(samples)))


class TestWhatDoesNotReachTheDetector:
    def test_neither_the_backlog_nor_the_app_s_own_voice_is_recorded(self) -> None:
        context: Any = FakeContext(frames(*ECHO_THEN_TURN), backlog=STALE)

        audio = continuous.collect_turn(context, FakeStatus(), skip_seconds=1.0)

        # Half a second of room, a second of speech, and the second of silence that
        # ends the turn. Nothing in it is louder than the learner spoke, which is
        # what says that neither the stale seconds nor the echo got in.
        assert seconds_of(audio) == pytest.approx(2.5, abs=0.05)
        assert loudest(audio) == pytest.approx(SPEECH, abs=0.01)

    def test_the_backlog_alone_would_stop_the_turn_from_ever_ending(self) -> None:
        # Why draining is not merely tidy. The detector sets its noise floor from the
        # first half second it is given; hand it the loud backlog and the floor lands
        # above the learner's voice, so the learner never registers as speaking and
        # the turn never closes. Here the backlog is fed as live audio to show it.
        context: Any = FakeContext(STALE + frames(*ECHO_THEN_TURN))

        assert continuous.collect_turn(context, FakeStatus(), skip_seconds=0.0) is None

    def test_a_reply_that_never_played_still_drains(self) -> None:
        # Synthesis failing reports zero seconds, which turns the echo discard off.
        # The backlog is not conditional on it: those seconds are in the past either
        # way.
        context: Any = FakeContext(
            frames((0.5, QUIET), (1.0, SPEECH), (1.2, QUIET)), backlog=STALE
        )

        audio = continuous.collect_turn(context, FakeStatus(), skip_seconds=0.0)

        assert seconds_of(audio) == pytest.approx(2.5, abs=0.05)
        assert loudest(audio) == pytest.approx(SPEECH, abs=0.01)

    def test_draining_stops_at_a_queue_s_worth(self) -> None:
        # The drain stops when a batch comes back holding one frame, because that is
        # the receiver saying the queue was empty. A stream that always has two
        # frames ready never says it, so the count is what ends the drain — without
        # it this loop reads until the stream dies and the learner is never heard.
        context: Any = FakeContext([])
        supply = frames((continuous.BACKLOG_LIMIT * FRAME, BACKLOG)) + frames(
            (0.5, QUIET), (1.0, SPEECH), (1.2, QUIET)
        )
        context.audio_receiver = BurstReceiver(supply)

        audio = continuous.collect_turn(context, FakeStatus(), skip_seconds=0.0)

        assert seconds_of(audio) == pytest.approx(2.5, abs=0.05)
        assert loudest(audio) == pytest.approx(SPEECH, abs=0.01)


class TestTheStreamIsNotUp:
    def test_says_so_and_returns_nothing(self) -> None:
        # A hall with a locked-down network is a place this has to keep working,
        # not a place to show an error.
        status = FakeStatus()
        context: Any = FakeContext([], playing=False)

        assert continuous.collect_turn(context, status) is None
        assert status.captions == ["Starting the microphone…"]

    def test_a_stalled_stream_is_not_a_crash(self) -> None:
        context: Any = FakeContext(frames((0.5, QUIET), (0.2, SPEECH)))

        assert continuous.collect_turn(context, FakeStatus()) is None
