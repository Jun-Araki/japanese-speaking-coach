"""Tests for deciding when a spoken turn has ended.

No microphone and no network: the detector takes frames of numbers, so it is fed
numbers. What is pinned is the behaviour that decides whether the feature is usable
at all — a turn that ends too early cuts a beginner off mid-sentence, and one that
never ends leaves the microphone open.
"""

from __future__ import annotations

from speech.listen import QUIET_FLOOR, TurnDetector, loudness

FRAME = 0.02  # 20ms, the size WebRTC delivers


def quiet(level: float = 0.001) -> list[float]:
    return [level, -level] * 160


def speech(level: float = 0.2) -> list[float]:
    return [level, -level] * 160


def feed(detector: TurnDetector, frame: list[float], seconds: float) -> bool:
    """Push `seconds` worth of one kind of frame. True if the turn ended.

    `any` short-circuits, so feeding stops at the first frame that ends the turn —
    which is what the caller does too.
    """
    return any(detector.push(frame, FRAME) for _ in range(int(seconds / FRAME)))


class TestLoudness:
    def test_silence_is_zero(self) -> None:
        assert loudness([0.0] * 100) == 0.0

    def test_a_single_click_does_not_dominate(self) -> None:
        # RMS rather than peak: one loud sample among quiet ones is a chair scrape,
        # not somebody talking.
        click = [0.0] * 99 + [1.0]

        assert loudness(click) < 0.2

    def test_no_samples_is_not_an_error(self) -> None:
        assert loudness([]) == 0.0


class TestTurnEnds:
    def test_after_a_second_of_silence(self) -> None:
        detector = TurnDetector()
        feed(detector, quiet(), 0.5)  # calibration
        assert not feed(detector, speech(), 1.0)

        assert feed(detector, quiet(), 1.0)

    def test_not_before_anyone_has_spoken(self) -> None:
        # A microphone that opens on a quiet room must wait. Ending here would end
        # every turn before it began.
        detector = TurnDetector()

        assert not feed(detector, quiet(), 5.0)
        assert not detector.started

    def test_a_pause_for_thought_does_not_end_it(self) -> None:
        # Beginners stop in the middle of a sentence. Half a second of silence is
        # thinking; a whole second is finishing.
        detector = TurnDetector()
        feed(detector, quiet(), 0.5)
        feed(detector, speech(), 0.6)

        assert not feed(detector, quiet(), 0.6)
        assert not feed(detector, speech(), 0.3)

    def test_a_cough_is_not_a_turn(self) -> None:
        # Loud enough to clear the floor, too short to be speech, so the turn never
        # starts and the silence after it ends nothing.
        detector = TurnDetector()
        feed(detector, quiet(), 0.5)
        feed(detector, speech(), 0.1)

        assert not feed(detector, quiet(), 2.0)
        assert not detector.started

    def test_an_open_microphone_is_closed_eventually(self) -> None:
        # Someone talking without pause, or a phone in a pocket. The correction
        # engine judges one sentence, and thirty seconds is not one sentence.
        detector = TurnDetector(max_turn=2.0)
        feed(detector, quiet(), 0.5)

        assert feed(detector, speech(), 3.0)
        assert detector.timed_out


class TestTheFloorAdaptsToTheRoom:
    def test_a_noisy_room_raises_the_floor(self) -> None:
        # A fixed threshold never falls below a café's noise, and the turn would
        # never end. The floor is measured from the room itself.
        noisy = TurnDetector()
        feed(noisy, quiet(level=0.05), 0.5)

        silent = TurnDetector()
        feed(silent, quiet(level=0.0), 0.5)

        assert noisy.floor > silent.floor

    def test_a_silent_input_keeps_a_floor_above_zero(self) -> None:
        # Otherwise every frame clears a floor of zero and the room's own hiss reads
        # as continuous speech.
        detector = TurnDetector()
        feed(detector, quiet(level=0.0), 0.5)

        assert detector.floor >= QUIET_FLOOR

    def test_room_noise_below_the_floor_never_starts_a_turn(self) -> None:
        detector = TurnDetector()
        feed(detector, quiet(level=0.02), 0.5)

        assert not feed(detector, quiet(level=0.02), 5.0)
