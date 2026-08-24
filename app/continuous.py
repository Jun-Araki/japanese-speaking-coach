"""Listening without a button: the microphone stays open, and silence ends the turn.

BEHIND A FLAG, WITH THE OLD PATH INTACT. This needs WebRTC, which needs a STUN
server and sometimes a TURN server, and whether it connects from a hall in Bangalore
on 13 September is not knowable from here. `CONTINUOUS_VOICE=0` puts the press-to-talk
screen back with one environment variable and no deploy.

WHAT RUNS WHERE. The browser captures audio and streams it; this loop pulls frames
off that stream, hands each to the turn detector, and stops at the first frame that
ends the turn. The transcription and the reply happen afterwards, on the assembled
audio, exactly as they do for a recording made with a button — the correction path is
untouched, so the published numbers still describe it.

STILL NOTHING IS STORED. Frames are held in memory for the length of one turn and
dropped when it is sent.
"""

from __future__ import annotations

import os
from typing import Any, Final

import av
import numpy as np
from streamlit_webrtc import WebRtcMode, webrtc_streamer

from speech.listen import MAX_TURN, TurnDetector
from speech.voice import wav_header

# Google's public STUN is enough to discover an address; it is not a relay. Networks
# that block direct connections need a TURN server, which is an account and a bill,
# and the flag above is what covers that case until there is one.
RTC_CONFIGURATION: Final[dict[str, Any]] = {
    "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
}

# The rate the audio is resampled to before it is sent for transcription. 16kHz is
# what speech models expect and a quarter of the bytes of 48kHz.
TARGET_RATE: Final = 16_000

# How long to wait for the next frame before giving up on the stream.
FRAME_TIMEOUT: Final = 3.0

# How many frames the receiver queues before it starts dropping the oldest, at 20ms
# each: about five seconds.
#
# ONE NUMBER, USED TWICE, BECAUSE THE LOG ASKS FOR TROUBLE. A busy stream prints
# "Queue overflow. Consider to set receiver size bigger. Current size is 256" — seen
# on the deployment on 2026-08-24 — and taking that advice without reading this would
# break the turn detector. The drain below stops after a queue's worth so that a
# bursting stream cannot hold it for ever; raise the queue alone and the drain gives
# up partway through the backlog, handing the detector seconds of audio recorded
# before the turn began. Its noise floor comes from the first half second it is given,
# so that audio would become the definition of silence.
#
# The overflow itself is not a fault. The script spends seconds transcribing,
# replying and synthesising, and whatever arrives meanwhile is dropped — which is
# fine, because the drain discards exactly that audio on purpose.
RECEIVER_SIZE: Final = 256
BACKLOG_LIMIT: Final = RECEIVER_SIZE


def enabled() -> bool:
    """Whether to listen continuously. Off puts the button back."""
    return os.environ.get("CONTINUOUS_VOICE", "1").strip().lower() not in {"0", "false", "no"}


def _mono_16k(frame: av.AudioFrame) -> np.ndarray:
    """One frame as mono float samples at the target rate.

    PACKED AND PLANAR ARE BOTH STEREO AND LOOK NOTHING ALIKE, and getting that wrong
    doubled every duration in this file until 2026-08-23. aiortc's Opus decoder is
    fixed to `format="s16"`, `layout="stereo"` — s16 is PACKED, so `to_ndarray()`
    returns a single row of interleaved LRLRLR samples, shape (1, 1920) for a 20ms
    frame. Averaging rows, which is right for planar (2, 960), does nothing to that
    single row: all 1920 samples survived, a third of them were kept by the
    downsampling step, and 640 samples came back for 20ms of sound that should have
    produced 320.

    Everything downstream then ran on a clock that was exactly twice too fast. The
    turn ended after half a second of silence rather than one — the cut-off
    mid-sentence that speech/listen.py exists to avoid — a turn could run 15 seconds
    rather than 30, and the WAV handed to the transcriber carried a 16kHz header over
    samples worth 32kHz, so every spoken turn since the microphone stopped needing a
    button was transcribed at half speed.

    The channel count comes from the layout rather than from the array's shape,
    because the shape cannot tell one channel from two when the samples are packed.
    """
    raw = frame.to_ndarray()
    channels = len(frame.layout.channels)
    array = raw.astype(np.float32)
    if array.ndim > 1 and array.shape[0] > 1:
        # Planar: one row per channel.
        array = array.mean(axis=0)
    else:
        array = array.reshape(-1)
        if channels > 1:
            # Packed: LRLRLR. Averaged rather than decimated, so that a headset with
            # one live side does not read as half the loudness.
            array = array.reshape(-1, channels).mean(axis=1)
    if np.issubdtype(raw.dtype, np.integer):
        array = array / 32768.0
    if frame.sample_rate and frame.sample_rate != TARGET_RATE:
        # Nearest-sample resampling. Crude, and adequate: the detector reads loudness,
        # and a beginner's sentence survives it — which is checked, not assumed, by
        # tests/test_continuous.py timing a real decoded frame.
        step = frame.sample_rate / TARGET_RATE
        index = (np.arange(int(len(array) / step)) * step).astype(int)
        array = array[index]
    return array


def _wav(chunks: list[np.ndarray]) -> bytes:
    """The turn's audio as a WAV file the transcriber will accept."""
    samples = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767).astype("<i2")
    return wav_header(len(pcm.tobytes()), rate=TARGET_RATE) + pcm.tobytes()


# TWO CALLS, NOT ONE, AND THE SPLIT IS THE POINT. This used to be a single `listen()`
# that drew the widget and then blocked in the frame loop until the learner stopped
# talking. Everything the screen wanted to draw after the input box — the reply being
# read aloud, the button that ends the conversation — therefore never ran on any turn
# where the microphone actually connected: the loop did not return, and the rerun that
# followed it wiped the run. The audio only played when the stream had FAILED, which
# is a feature that works when it is broken.
#
# So opening the microphone and collecting from it are separate calls now, and
# everything that has to reach the page goes between them.


def open_stream() -> Any:
    """Put the microphone on the page and return at once, without waiting for a word.

    Draws the widget and nothing else. The returned context is handed back to
    `collect_turn` once the rest of the page has been drawn.
    """
    return webrtc_streamer(
        key="listener",
        mode=WebRtcMode.SENDONLY,
        audio_receiver_size=RECEIVER_SIZE,
        rtc_configuration=RTC_CONFIGURATION,
        media_stream_constraints={"audio": True, "video": False},
        desired_playing_state=True,
    )


def is_live(context: Any) -> bool:
    """Whether the stream is actually carrying audio right now.

    Asked before the turn is collected, so the screen can put a record button up when
    the answer is no. WebRTC needs a network that will carry it and this app has STUN
    and no TURN, so "no" is a state a hall can hold it in indefinitely.
    """
    return bool(context.state.playing) and context.audio_receiver is not None


def collect_turn(context: Any, status: Any, skip_seconds: float = 0.0) -> bytes | None:
    """Stream until the turn ends. Returns the audio, or None if it did not.

    The loop belongs to one script run: Streamlit reruns after a turn is sent, and
    the next run starts a new detector. That is why the detector holds no audio and
    the caller holds no detector.

    Two things are thrown away before the detector is fed anything, and they are not
    the same thing.

    THE BACKLOG, WHICH IS THE PAST. The receiver is a queue holding the last five
    seconds of sound, not a live tap: by the time this is called the script has spent
    seconds transcribing, replying and synthesising, and every one of those seconds is
    sitting in the queue waiting to be read. None of it can be an answer to a reply the
    learner had not heard yet, and feeding it to the detector is worse than losing it —
    the detector sets its noise floor from the first half second it is given, so the
    tail of the learner's PREVIOUS sentence would become the definition of silence.
    So the queue is emptied first. `get_frames` hands back the whole backlog in one
    call and blocks for a single frame when there is none, so a batch of one is how
    "caught up with real time" announces itself.

    THEN `skip_seconds`, WHICH IS THE APP TALKING. The reply is handed to the browser
    to play immediately before this is called, so the next few seconds of microphone
    may be the app's own voice — and a detector that hears the app speak decides the
    learner spoke, then decides they stopped, and sends the app's own sentence back to
    be corrected. Browsers do echo cancellation by default and it would probably not
    happen; "probably" is not a thing to find out in a hall on 13 September.

    THE ORDER OF THOSE TWO IS THE WHOLE POINT, and getting it wrong is not a smaller
    version of getting it right. Discarding `skip_seconds` without draining first
    discards `skip_seconds` OF THE BACKLOG — seconds recorded before the reply existed
    — and lets the echo through untouched. Written that way on 2026-08-22 and caught
    the same day by reading the receiver's implementation rather than the tests, which
    were passing because the fake queue had no backlog to be wrong about.

    WHAT IT COSTS: a learner who reads the reply on screen and starts answering before
    it is spoken has that beginning dropped. That is the same trade already made by
    drawing the input box first — they can act on the reply early, and the audio for
    that turn is what gives way.
    """
    if not is_live(context):
        status.caption(
            "Starting the microphone… if it does not connect, use the button or type."
        )
        return None

    detector = TurnDetector()
    chunks: list[np.ndarray] = []
    dropped = 0.0
    status.caption("Listening. Speak when you are ready — I will wait for you to stop.")

    read = 0
    while read < BACKLOG_LIMIT:
        try:
            backlog = context.audio_receiver.get_frames(timeout=FRAME_TIMEOUT)
        except Exception:  # noqa: BLE001 - a stalled stream is not a crash
            return None
        read += len(backlog)
        if len(backlog) <= 1:
            break

    while True:
        try:
            frames = context.audio_receiver.get_frames(timeout=FRAME_TIMEOUT)
        except Exception:  # noqa: BLE001 - a stalled stream is not a crash
            return None
        if not frames:
            continue
        for frame in frames:
            samples = _mono_16k(frame)
            seconds = len(samples) / TARGET_RATE
            if dropped < skip_seconds:
                # Not kept and not judged: these frames may be the app's own voice.
                dropped += seconds
                continue
            chunks.append(samples)
            if detector.push(samples.tolist(), seconds):
                if detector.timed_out:
                    status.caption(
                        f"That was over {int(MAX_TURN)} seconds, so I stopped there."
                    )
                return _wav(chunks)
