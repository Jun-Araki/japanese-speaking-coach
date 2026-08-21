"""Deciding when a spoken turn has ended, from the audio alone.

THE RULE: the turn ends after one second of silence, once the learner has actually
started speaking. Not before — a microphone that opens and immediately hears a quiet
room must wait, or every turn ends before it begins.

ENERGY, NOT A MODEL. Silence is detected from the loudness of each frame against a
floor, which is a few lines of arithmetic rather than a second neural network in the
request path. The planning document already argued this is enough in a quiet room,
and a meetup table is quiet enough for a phone held near the face. What it cannot do
is separate one speaker from another in a noisy room; that limitation is real and is
why the press-to-talk path stays.

THE FLOOR ADAPTS TO THE ROOM. A fixed threshold is wrong twice over: a phone in a
café never falls below it and the turn never ends, and a good microphone in a quiet
room sits under it and the first syllable is treated as silence. So the floor is set
from the room's own noise, measured over the first frames before anyone speaks.

NOTHING HERE TOUCHES THE NETWORK. It takes frames in and returns a verdict, so it is
tested against arrays rather than against a microphone.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final

# How long the room has to stay quiet before the turn is over. A shorter gap cuts
# people off mid-sentence — beginners pause to think in the middle of one.
SILENCE_TO_END: Final = 1.0

# Nothing is sent until this much speech has been heard. A cough or a chair scrape
# clears the loudness floor and would otherwise open and close a turn on its own.
MIN_SPEECH: Final = 0.35

# A turn cannot run forever: an open microphone in a pocket is a bill. The correction
# engine also judges one sentence, and a minute of speech is not one sentence.
MAX_TURN: Final = 30.0

# The room is sampled for this long before speech is expected, and the floor is set
# from what it heard.
CALIBRATION: Final = 0.5

# How far above the room's own noise a frame has to be to count as speech. Measured
# as a multiplier rather than an offset because loudness here is a ratio scale.
SPEECH_OVER_NOISE: Final = 3.0

# Used until the room has been measured, and as a floor under the measured value so
# that a perfectly silent input does not make every frame look like speech.
QUIET_FLOOR: Final = 0.005


def loudness(samples: list[float]) -> float:
    """Root mean square of one frame, in the same units as the samples.

    RMS rather than peak: a single click is not speech, and peak treats it as the
    loudest thing in the room.
    """
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


@dataclass
class TurnDetector:
    """Frame by frame, decides whether the learner has finished speaking.

    Fed by whatever is pulling audio off the wire. Holds no audio itself — the caller
    keeps the frames it wants to send — so this stays testable and forgets nothing it
    was not given.
    """

    silence_to_end: float = SILENCE_TO_END
    min_speech: float = MIN_SPEECH
    max_turn: float = MAX_TURN
    calibration: float = CALIBRATION

    heard: float = 0.0
    speech: float = 0.0
    silence: float = 0.0
    started: bool = False
    _noise: list[float] = field(default_factory=list)
    _floor: float = QUIET_FLOOR

    @property
    def floor(self) -> float:
        return self._floor

    def push(self, samples: list[float], seconds: float) -> bool:
        """Add one frame. True when the turn is over and should be sent.

        Returns True at most once for a turn; the caller stops feeding it and starts
        a fresh detector for the next one.
        """
        self.heard += seconds
        level = loudness(samples)

        if self.heard <= self.calibration:
            # Still listening to the room. Frames here are never speech, however loud
            # — someone who starts talking during calibration is heard from the next
            # frame on, and half a second of a greeting is not worth a worse floor.
            self._noise.append(level)
            self._floor = max(QUIET_FLOOR, _median(self._noise) * SPEECH_OVER_NOISE)
            return False

        if level >= self._floor:
            self.speech += seconds
            self.silence = 0.0
            if self.speech >= self.min_speech:
                self.started = True
        elif self.started:
            self.silence += seconds

        if self.started and self.silence >= self.silence_to_end:
            return True
        return self.heard >= self.max_turn and self.started

    @property
    def timed_out(self) -> bool:
        """Whether the turn ended because it ran long rather than because it stopped."""
        return self.heard >= self.max_turn


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if not ordered:
        return 0.0
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2
