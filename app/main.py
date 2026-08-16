"""The conversation screen.

One screen with three states, as fixed in docs/ja/functional-design.md: pick a
scene and a level, talk, then look back at it. This is text only -- voice arrives
late in the schedule (late October), and putting it in before the corrections are any
good would make a bad number impossible to attribute to either the transcription or
the correction.

Corrections run on every turn but nothing about them reaches the conversation
state. They are collected out of sight and only the review renders them.
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from correction import CorrectionResult, check, validate  # noqa: E402
from dialogue import LEVELS, SCENES, Utterance, opening_line, reply  # noqa: E402

load_dotenv()

st.set_page_config(page_title="Japanese Speaking Coach", page_icon="🗣️")

SESSION_KEYS = ("scene", "level", "history", "failure", "corrections")


def history() -> list[Utterance]:
    if "history" not in st.session_state:
        st.session_state["history"] = []
    result: list[Utterance] = st.session_state["history"]
    return result


def corrections() -> list[CorrectionResult]:
    if "corrections" not in st.session_state:
        st.session_state["corrections"] = []
    result: list[CorrectionResult] = st.session_state["corrections"]
    return result


def start_session(scene: str, level: str) -> None:
    st.session_state.pop("review", None)
    st.session_state["scene"] = scene
    st.session_state["level"] = level
    st.session_state["failure"] = None
    st.session_state["history"] = [Utterance("partner", opening_line(scene))]
    st.session_state["corrections"] = []


def end_session() -> None:
    st.session_state["review"] = corrections()
    for key in SESSION_KEYS:
        st.session_state.pop(key, None)


def record_correction(sentence: str, scene: str, level: str) -> None:
    """Judge one learner sentence and put the result away until the review.

    A correction that fails must not interrupt the conversation: the learner is
    mid-sentence and the result is not due until they finish. The sentence is still
    recorded, with nothing attached, so a failure shows up as a gap in the review
    instead of vanishing.
    """
    try:
        result = check(sentence, scene, level)
        # The deterministic checks run here rather than inside `check`, so that the
        # measurement can score the same answers with them on and off. The learner
        # sees the validated version; the scorer decides per run (evals/score.py).
        if result.correction is not None:
            checked = validate(sentence, result.correction)
            result = replace(result, correction=checked.correction)
    except Exception:
        result = CorrectionResult(sentence, correction=None, attempts=0, format_problems=())
    corrections().append(result)


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
        learner_sentence = history()[-1].text
        with st.chat_message("assistant"), st.spinner("…"):
            try:
                answer = reply(scene, level, history())
            except Exception as exc:  # shown to the learner, never swallowed
                st.session_state["failure"] = f"{type(exc).__name__}: {exc}"
                st.rerun()
            else:
                history().append(Utterance("partner", answer))
                st.write(answer)
                # After the reply is on screen, and never rendered: the whole point
                # of a separate correction call is that the learner does not see it
                # until they have stopped talking.
                record_correction(learner_sentence, scene, level)

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
    if st.button("End the conversation"):
        end_session()
        st.rerun()


def render_review() -> None:
    results: list[CorrectionResult] = st.session_state["review"]
    checked = [result for result in results if result.correction is not None]
    to_change = [
        result
        for result in checked
        if result.correction is not None and result.correction.needs_correction
    ]

    st.title("Review")

    if not results:
        st.write("You did not say anything this time, so there is nothing to look back at.")
    else:
        st.write(
            f"You said {len(results)} "
            f"{'sentence' if len(results) == 1 else 'sentences'}. "
            f"{len(to_change)} of them would sound better said another way."
        )

    for result in results:
        answer = result.correction
        if answer is None:
            continue
        with st.container(border=True):
            st.markdown(f"**{result.learner_sentence}**")
            if not answer.needs_correction:
                st.write("This one is fine as it is.")
            else:
                st.write(f"→ {answer.corrected_sentence}")
                if answer.reason_en:
                    st.caption(answer.reason_en)

    unchecked = len(results) - len(checked)
    if unchecked:
        # Saying nothing at all would read as "these were fine", which is the one
        # thing they are not known to be.
        st.caption(
            f"{unchecked} of your sentences could not be checked, so they are not "
            "listed above. That is a failure on our side, not on yours."
        )

    st.divider()
    if st.button("Start another conversation", type="primary"):
        st.session_state.pop("review", None)
        st.rerun()


if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
    st.error(
        "No API key found. GEMINI_API_KEY is read from the environment "
        "(~/.zshenv locally, app secrets once deployed) and is deliberately not "
        "stored in this repository."
    )
elif "scene" in st.session_state:
    render_conversation()
elif "review" in st.session_state:
    render_review()
else:
    render_setup()
