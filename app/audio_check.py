"""Smoke test for the audio path on iOS Safari.

Week 1 acceptance criterion: decide on 8/3 whether the browser can (1) record
through st.audio_input and (2) play back through st.audio(autoplay=True). The two
are judged separately -- only a recording failure justifies falling back to text.

The 8/3 run showed autoplay firing on the first press and staying silent on every
press after it, without a reload. The first version of this page replayed one
identical tone, which cannot tell apart the two possible causes:

  (1) Streamlit addresses media by content hash, so identical bytes resolve to the
      same element and the browser never starts a second playback. Harmless -- in
      the real app every reply is different audio.
  (2) Safari allows one autoplay per page load. Serious -- every turn after the
      first would need a tap.

So the tone now changes pitch on every press. If sound keeps coming, the cause is
(1) and week 3 can rely on autoplay. If it stops after the first, the cause is (2)
and week 3 needs a visible play button.

Throwaway page. It is not wired to the conversation and is deleted once the result
is written into .steering/20260802-week1-baseline/design.md.
"""

from __future__ import annotations

import io
import math
import struct
import time
import wave

import streamlit as st

SAMPLE_RATE = 22_050
TONE_SECONDS = 1.5
# Loud enough to hear on a phone speaker in a quiet room, quiet enough not to startle.
TONE_AMPLITUDE = 0.35
# A4, C5, E5, G5 -- far enough apart to tell by ear which press produced the sound.
TONE_PITCHES = (440.0, 523.0, 659.0, 784.0)
PITCH_NAMES = ("ラ", "ド", "ミ", "ソ")
# Stands in for the round trip to the model, which is what breaks the user-gesture
# window in the real app.
SIMULATED_MODEL_DELAY_SECONDS = 3


def build_tone_wav(pitch_hz: float) -> bytes:
    """Return a short sine-wave WAV, so autoplay can be tested without a recording."""
    frame_count = int(SAMPLE_RATE * TONE_SECONDS)
    fade_frames = frame_count * 0.1
    frames = bytearray()
    for i in range(frame_count):
        # Without a fade-out the abrupt stop clicks audibly on phone speakers.
        fade = min(1.0, (frame_count - i) / fade_frames)
        value = TONE_AMPLITUDE * fade * math.sin(2 * math.pi * pitch_hz * i / SAMPLE_RATE)
        frames += struct.pack("<h", int(value * 32767))

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(frames))
    return buffer.getvalue()


def next_tone() -> tuple[bytes, str]:
    """Return a tone one step up from the previous press, plus its name."""
    index = int(st.session_state.get("press_count", 0))
    st.session_state["press_count"] = index + 1
    position = index % len(TONE_PITCHES)
    return build_tone_wav(TONE_PITCHES[position]), PITCH_NAMES[position]


st.set_page_config(page_title="音声の疎通確認", page_icon="🎙️")

st.title("音声の疎通確認（8/3）")
st.caption(
    "iPhone Safari の実機で開くこと。**URL が https:// で始まっていない場合、"
    "コードが正しくてもマイクは動きません**（判定を誤るので必ず確認）。"
)

st.header("① 録音できるか")
st.caption("`st.audio_input` — 駄目ならテキスト方式へ戻す判断を今日下す")

recording = st.audio_input("マイクを押して、日本語で一言話してください")

if recording is None:
    st.info("まだ録音されていません。")
else:
    st.success(f"録音できました（{len(recording.getvalue()):,} バイト）")
    st.audio(recording)
    st.caption("↑ 再生して自分の声が入っているか確認。**無音なら①は失敗**です。")

st.header("② 自動再生できるか")
st.caption("`st.audio(autoplay=True)` — 駄目でも音声は降ろさない。再生ボタン方式に落とす")

st.warning(
    "**リロードせずに、各ボタンを2〜3回ずつ押してください。**\n\n"
    "知りたいのは「1回目が鳴るか」ではなく、**「2回目以降も鳴るか」**です。"
)

st.subheader("②-A　押した直後に鳴るか（毎回ちがう音）")
if st.button("すぐ再生する", use_container_width=True):
    tone, name = next_tone()
    st.audio(tone, format="audio/wav", autoplay=True)
    st.caption(f"いま鳴るはずの音：**{name}**。プレイヤーに触らず鳴れば成功。")

st.subheader("②-B　3秒待ってから鳴るか（毎回ちがう音）")
st.caption(
    "**本番で効くのはこちら。** 実際の会話では話し終えてから AI の返事が返るまで数秒かかり、"
    "その間に「ユーザー操作の直後」という扱いが切れると iOS Safari は自動再生を止めます。"
)
if st.button("3秒待って再生する", use_container_width=True):
    with st.spinner("AI の応答を待っている想定で3秒待ちます…"):
        time.sleep(SIMULATED_MODEL_DELAY_SECONDS)
    tone, name = next_tone()
    st.audio(tone, format="audio/wav", autoplay=True)
    st.caption(f"いま鳴るはずの音：**{name}**。")

st.subheader("②-C　わざと同じ音を鳴らす（比較用）")
st.caption(
    "こちらは何度押しても必ず「ラ」。"
    "**A・B は鳴るのにこれだけ鳴らない**なら、原因は音声の同一性です。"
)
if st.button("同じ音（ラ）を鳴らす", use_container_width=True):
    st.audio(build_tone_wav(TONE_PITCHES[0]), format="audio/wav", autoplay=True)

st.caption(f"②-A と ②-B を押した回数：{int(st.session_state.get('press_count', 0))}")

st.divider()

st.header("判定")
st.markdown(
    """
| 結果 | 判断 |
|---|---|
| **①が駄目** | テキスト方式へ戻す判断を**今日**下す |
| **A・B が毎回鳴る** | 同じ音声だから鳴らないだけ。**自動再生でいける** |
| **A・B も1回きり** | 「再生ボタン」方式へ。**音声は降ろさない** |
"""
)
st.caption("結果は `.steering/20260802-week1-baseline/design.md` に記録すること。")

with st.expander("実行環境（確認用）"):
    st.write("User-Agent:", st.context.headers.get("User-Agent", "取得できず"))
    st.write("Streamlit:", st.__version__)
