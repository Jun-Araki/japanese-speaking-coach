"""The conversation screen.

One screen with two states, as fixed in docs/ja/functional-design.md: pick a scene
and a level, then talk. Week 1 is text only -- voice arrives in week 3, and putting
it in before the corrections are any good would make a bad number impossible to
attribute to either the transcription or the correction.

Corrections are deliberately absent from this screen. They are computed per turn
and shown only after the session ends (day 3), never during the conversation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dialogue import LEVELS, SCENES, Utterance, opening_line, reply  # noqa: E402

load_dotenv()

st.set_page_config(page_title="Japanese Speaking Coach", page_icon="🗣️")


def history() -> list[Utterance]:
    if "history" not in st.session_state:
        st.session_state["history"] = []
    result: list[Utterance] = st.session_state["history"]
    return result


def start_session(scene: str, level: str) -> None:
    st.session_state["scene"] = scene
    st.session_state["level"] = level
    st.session_state["failure"] = None
    st.session_state["history"] = [Utterance("partner", opening_line(scene))]


def end_session() -> None:
    for key in ("scene", "level", "history", "failure"):
        st.session_state.pop(key, None)


def render_setup() -> None:
    st.title("Japanese Speaking Coach")
    st.write(
        "Have a short conversation in Japanese. Nothing is corrected while you talk — "
        "you get the corrections, and the reason for each one in English, once you finish."
    )

    scene = st.selectbox(
        "What do you want to practise?",
        options=list(SCENES),
        format_func=lambda key: SCENES[key],
    )
    level = st.selectbox(
        "How much Japanese do you have?",
        options=list(LEVELS),
        format_func=lambda key: LEVELS[key],
    )

    if st.button("Start", type="primary", use_container_width=True):
        start_session(scene, level)
        st.rerun()

    st.caption(
        "Your sentences are sent to an AI model to generate the reply and the "
        "corrections. Do not type anything you would not want to share."
    )


def render_conversation() -> None:
    scene: str = st.session_state["scene"]
    level: str = st.session_state["level"]

    st.title(SCENES[scene])
    st.caption(f"{LEVELS[level]} · write in Japanese · corrections come at the end")

    for utterance in history():
        role = "user" if utterance.speaker == "learner" else "assistant"
        with st.chat_message(role):
            st.write(utterance.text)

    awaiting_reply = bool(history()) and history()[-1].speaker == "learner"
    failure: str | None = st.session_state.get("failure")

    if awaiting_reply and failure is None:
        with st.chat_message("assistant"), st.spinner("…"):
            try:
                answer = reply(scene, level, history())
            except Exception as exc:  # shown to the learner, never swallowed
                st.session_state["failure"] = f"{type(exc).__name__}: {exc}"
                st.rerun()
            else:
                history().append(Utterance("partner", answer))
                st.write(answer)

    if failure is not None:
        # A canned Japanese line here would read as a reply and teach the learner
        # something the model never said, so the failure is stated plainly instead.
        st.error(f"The reply could not be generated. {failure}")
        if st.button("Try again", type="primary"):
            st.session_state["failure"] = None
            st.rerun()

    if learner_text := st.chat_input("日本語で書いてください"):
        history().append(Utterance("learner", learner_text))
        st.session_state["failure"] = None
        st.rerun()

    st.divider()
    # Day 3 puts the review between this button and the setup screen.
    if st.button("End the conversation"):
        end_session()
        st.rerun()


if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
    st.error(
        "No API key found. GEMINI_API_KEY is read from the environment "
        "(~/.zshenv locally, app secrets once deployed) and is deliberately not "
        "stored in this repository."
    )
elif "scene" in st.session_state:
    render_conversation()
else:
    render_setup()
