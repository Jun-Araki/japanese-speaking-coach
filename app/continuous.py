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


def enabled() -> bool:
    """Whether to listen continuously. Off puts the button back."""
    return os.environ.get("CONTINUOUS_VOICE", "1").strip().lower() not in {"0", "false", "no"}


def _mono_16k(frame: av.AudioFrame) -> np.ndarray:
    """One frame as mono float samples at the target rate."""
    array = frame.to_ndarray()
    # Interleaved stereo arrives as one row; average the channels so a headset with
    # one live side does not read as half the loudness.
    if array.ndim > 1 and array.shape[0] > 1:
        array = array.mean(axis=0)
    array = array.reshape(-1).astype(np.float32)
    if np.issubdtype(frame.to_ndarray().dtype, np.integer):
        array = array / 32768.0
    if frame.sample_rate and frame.sample_rate != TARGET_RATE:
        # Nearest-sample resampling. Crude, and adequate: the detector reads loudness,
        # and the transcriber is given the original frames re-encoded rather than this.
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


def listen(status: Any) -> bytes | None:
    """Stream until the turn ends. Returns the audio, or None if it did not.

    The loop belongs to one script run: Streamlit reruns after a turn is sent, and
    the next run starts a new detector. That is why the detector holds no audio and
    the caller holds no detector.
    """
    context = webrtc_streamer(
        key="listener",
        mode=WebRtcMode.SENDONLY,
        audio_receiver_size=256,
        rtc_configuration=RTC_CONFIGURATION,
        media_stream_constraints={"audio": True, "video": False},
        desired_playing_state=True,
    )
    if not context.state.playing or context.audio_receiver is None:
        status.caption("Starting the microphone…")
        return None

    detector = TurnDetector()
    chunks: list[np.ndarray] = []
    status.caption("Listening. Speak when you are ready — I will wait for you to stop.")

    while True:
        try:
            frames = context.audio_receiver.get_frames(timeout=FRAME_TIMEOUT)
        except Exception:  # noqa: BLE001 - a stalled stream is not a crash
            return None
        if not frames:
            continue
        for frame in frames:
            samples = _mono_16k(frame)
            chunks.append(samples)
            seconds = len(samples) / TARGET_RATE
            if detector.push(samples.tolist(), seconds):
                if detector.timed_out:
                    status.caption(
                        f"That was over {int(MAX_TURN)} seconds, so I stopped there."
                    )
                return _wav(chunks)
