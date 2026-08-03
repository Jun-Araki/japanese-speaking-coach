"""Smoke test for the audio path on iOS Safari.

Week 1 acceptance criterion: decide on 8/3 whether the browser can (1) record
through st.audio_input and (2) play back through st.audio(autoplay=True). The two
are judged separately -- only a recording failure justifies falling back to text.

Throwaway page. It is not wired to the conversation and is deleted once the
result is written into .steering/20260802-week1-baseline/design.md.
"""

from __future__ import annotations

import io
import math
import struct
import time
import wave

import streamlit as st

SAMPLE_RATE = 22_050
TONE_HZ = 440.0
TONE_SECONDS = 1.5
# Loud enough to hear on a phone speaker in a quiet room, quiet enough not to startle.
TONE_AMPLITUDE = 0.35
# Stands in for the round trip to the model, which is what breaks the user-gesture
# window in the real app.
SIMULATED_MODEL_DELAY_SECONDS = 3


def build_tone_wav() -> bytes:
    """Return a short sine-wave WAV, so autoplay can be tested without a recording."""
    frame_count = int(SAMPLE_RATE * TONE_SECONDS)
    fade_frames = frame_count * 0.1
    frames = bytearray()
    for i in range(frame_count):
        # Without a fade-out the abrupt stop clicks audibly on phone speakers.
        fade = min(1.0, (frame_count - i) / fade_frames)
        value = TONE_AMPLITUDE * fade * math.sin(2 * math.pi * TONE_HZ * i / SAMPLE_RATE)
        frames += struct.pack("<h", int(value * 32767))

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(frames))
    return buffer.getvalue()


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
    st.info(
        "まだ録音されていません。\n\n"
        "**操作の観察も課題です**：押して開始 → もう一度押して停止、という動きかどうか、"
        "マイクの許可を毎回聞かれるかを見てください。"
    )
else:
    st.success(f"録音できました（{len(recording.getvalue()):,} バイト）")
    st.audio(recording)
    st.caption("↑ 再生して自分の声が入っているか確認。**無音なら①は失敗**です。")

st.header("② 自動再生できるか")
st.caption("`st.audio(autoplay=True)` — 駄目でも音声は降ろさない。再生ボタン方式に落とす")

st.subheader("②-A　押した直後に鳴るか")
if st.button("すぐ再生する", use_container_width=True):
    st.audio(build_tone_wav(), format="audio/wav", autoplay=True)
    st.caption("再生ボタンを押さずに「ポー」と鳴れば成功。")

st.subheader("②-B　3秒待ってから鳴るか")
st.caption(
    "**本番で効くのはこちら。** 実際の会話では話し終えてから AI の返事が返るまで数秒かかり、"
    "その間に「ユーザー操作の直後」という扱いが切れると iOS Safari は自動再生を止めます。"
)
if st.button("3秒待って再生する", use_container_width=True):
    with st.spinner("AI の応答を待っている想定で3秒待ちます…"):
        time.sleep(SIMULATED_MODEL_DELAY_SECONDS)
    st.audio(build_tone_wav(), format="audio/wav", autoplay=True)
    st.caption("ここが鳴れば、第3週の読み上げはそのまま自動再生でいけます。")

st.divider()

st.header("判定")
st.markdown(
    """
| 結果 | 判断 |
|---|---|
| **①が駄目** | テキスト方式へ戻す判断を**今日**下す（先送りしない） |
| **②が両方駄目** | 自動再生を諦め「再生ボタン」方式で第3週へ。**音声は降ろさない** |
| **②-A のみ鳴る** | 同上。回避策は**第3週まで試さない**（今週の範囲外） |
| **全部動く** | そのまま第3週へ |
"""
)
st.caption("結果は `.steering/20260802-week1-baseline/design.md` に1行残すこと。")

with st.expander("実行環境（確認用）"):
    st.write("User-Agent:", st.context.headers.get("User-Agent", "取得できず"))
    st.write("Streamlit:", st.__version__)
