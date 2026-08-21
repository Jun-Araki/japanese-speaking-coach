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

from app.limits import (  # noqa: E402
    LimitReached,
    access_code,
    code_matches,
    max_turns,
    spend_tokens,
    spend_tts_chars,
)
from app.theme import CONTACT, NOTICE, SPEECH_CAVEAT, STYLE, VOICE_NOTICE  # noqa: E402
from correction import CorrectionResult  # noqa: E402
from dialogue import LEVELS, SCENES, Utterance, opening_line, reply  # noqa: E402
from graph.correction_graph import run as run_correction  # noqa: E402
from speech.voice import SpeechError, synthesise, transcribe  # noqa: E402

load_dotenv()


def _adopt_secrets() -> None:
    """Copy Streamlit's secrets into the environment, without overwriting it.

    Every other entry point — the API, the evaluation scripts, the container — reads
    `os.environ`, and `llm.py` is the single place the key is looked up. Community
    Cloud puts deployment secrets in `st.secrets`, so without this bridge the
    deployed app is the one caller that cannot find a key that is correctly set, and
    the failure looks like "no API key" on a page where one was configured.

    Local values win: a developer with a key already exported should not have it
    replaced by whatever is in a secrets file.
    """
    try:
        secrets = dict(st.secrets)
    except Exception:  # noqa: BLE001 - no secrets file locally is the normal case
        return
    for name, value in secrets.items():
        if isinstance(value, str) and not os.environ.get(name):
            os.environ[name] = value


_adopt_secrets()

st.set_page_config(page_title="Japanese Speaking Coach", page_icon="🗣️")
st.markdown(STYLE, unsafe_allow_html=True)

SESSION_KEYS = (
    "scene",
    "level",
    "history",
    "failure",
    "corrections",
    "caveat_seen",
    "used_speech",
)


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
    st.session_state["review_used_speech"] = bool(st.session_state.get("used_speech"))
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
        # Through the graph, which is also what the API calls: retrieve, correct,
        # validate. Two paths into one graph rather than two copies of the same
        # three steps — a screen that corrects differently from the endpoint is a
        # screen the measurements do not describe.
        state = run_correction(sentence, scene, level)
        result = replace(state["result"], correction=state.get("correction"))
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

    st.divider()
    st.markdown(NOTICE)
    st.caption(f"Questions, or want your session stopped mid-way? {CONTACT}")


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
                # Counted before the call, not after: a cap that is checked
                # afterwards is a cap the next request has already crossed. The
                # whole conversation goes into the estimate because the whole
                # conversation goes into the prompt.
                spend_tokens("".join(utterance.text for utterance in history()))
                answer = reply(scene, level, history())
            except LimitReached as capped:
                st.session_state["failure"] = str(capped)
                st.rerun()
            except Exception as exc:  # shown to the learner, never swallowed
                st.session_state["failure"] = f"{type(exc).__name__}: {exc}"
                st.rerun()
            else:
                history().append(Utterance("partner", answer))
                st.write(answer)
                speak(answer)
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

    learner_turns = sum(1 for utterance in history() if utterance.speaker == "learner")
    if learner_turns >= max_turns():
        # A cap reached mid-conversation ends it rather than silently ignoring what
        # is typed next: an input box that accepts a sentence and does nothing with
        # it is worse than no input box.
        st.info(
            f"This demo stops at {max_turns()} sentences per conversation. "
            "End the conversation to see your corrections."
        )
    else:
        render_input()

    st.divider()
    if st.button("End the conversation"):
        end_session()
        st.rerun()


def speak(text: str) -> None:
    """Read one line aloud, and say that the voice is synthetic.

    A failure here is a caption, not an error: the reply is already on screen and
    the conversation can continue without sound. Losing the audio is a smaller
    problem than an error box where a reply should be.
    """
    try:
        spend_tts_chars(text)
        audio = synthesise(text)
    except (LimitReached, SpeechError) as exc:
        st.caption(f"(no audio this time: {exc})")
        return
    st.audio(audio, format="audio/wav", autoplay=True)
    st.caption(VOICE_NOTICE)


def render_input() -> None:
    """Speak or type. What is transcribed is sent straight on.

    A CONFIRMATION STEP WAS BUILT AND THEN REMOVED (2026-08-21). It showed the
    transcription and asked "is this exactly what you said?" before sending, because
    transcription repairs learner mistakes and a repaired sentence is corrected as
    though the learner had said it. Used on the deployed app it cost a button press
    and a paragraph of English on every single turn, which for a beginner having a
    five-turn conversation is most of the interaction — so it went.

    What replaces it is not nothing. The transcription appears in the conversation as
    the learner's own line, where they can see it, and the review screen says that
    spoken sentences were transcribed and may have been altered. That is weaker than
    a gate and it is the trade that was chosen deliberately: a warning nobody reads
    because it blocks them protects nobody either.
    """
    if not st.session_state.get("caveat_seen"):
        # Once per session. Repeated above every recording, it trains people to skip
        # it, which costs more than the reminder gains.
        st.caption(SPEECH_CAVEAT)
        st.session_state["caveat_seen"] = True

    recording = st.audio_input("話してください")
    if recording is not None:
        with st.spinner("…"):
            try:
                heard = transcribe(recording.getvalue())
            except SpeechError as exc:
                st.warning(str(exc))
                return
        if not heard:
            st.warning("Nothing was heard. Please try again.")
            return
        history().append(Utterance("learner", heard))
        st.session_state["used_speech"] = True
        st.session_state["failure"] = None
        st.rerun()

    if typed := st.chat_input("または、日本語で書いてください"):
        history().append(Utterance("learner", typed))
        st.session_state["failure"] = None
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

    if st.session_state.get("review_used_speech"):
        # The one thing the removed confirmation step used to catch, said once where
        # it does not interrupt anything.
        st.caption(
            "Sentences you spoke were written down automatically. If a word came out "
            "differently from what you said, the correction above is for what was "
            "written down — not for what you said."
        )

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


def render_gate() -> None:
    """One shared code, asked once per session.

    Not a login: nobody is identified, nothing is remembered beyond this browser
    session, and everyone types the same string. Its one job is keeping a link that
    costs money per click from being open to the whole internet.
    """
    st.title("Japanese Speaking Coach")
    st.write("This demo is shared with a code. Please enter it to continue.")
    given = st.text_input("Access code", type="password")
    if st.button("Continue", type="primary"):
        if code_matches(given):
            st.session_state["unlocked"] = True
            st.rerun()
        else:
            st.error("That code is not right.")
    st.caption(f"No code? {CONTACT}")


if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
    st.error(
        "No API key found. GEMINI_API_KEY is read from the environment "
        "(~/.zshenv locally, app secrets once deployed) and is deliberately not "
        "stored in this repository."
    )
elif access_code() is not None and not st.session_state.get("unlocked"):
    render_gate()
elif "scene" in st.session_state:
    render_conversation()
elif "review" in st.session_state:
    render_review()
else:
    render_setup()
