"""The conversation screen.

One screen with three states, as fixed in docs/ja/functional-design.md: pick a
scene and a level, talk, then look back at it. Speech arrived on 2026-08-20, after
the corrections were measured and not before -- shipping it earlier would have made a
bad number impossible to attribute to either the transcription or the correction, and
the transcription turned out to repair the learner's mistakes, which is exactly the
kind of thing that has to be measurable separately.

Corrections run once, when the conversation is ended, and nothing about them
reaches the conversation state until the review renders them. They used to run on
every turn -- out of sight, but not out of the learner's way, since the turn waited
for them. See app/corrections.py.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import sys
import threading
from html import escape
from pathlib import Path
from typing import Any, Final

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import continuous  # noqa: E402
from app.corrections import correct_all  # noqa: E402
from app.limits import (  # noqa: E402
    LimitReached,
    access_code,
    code_matches,
    max_turns,
    spend_tokens,
    spend_tts_chars,
    start_tts_cooldown,
    tts_is_quiet,
)
from app.theme import CONTACT, NOTICE, SPEECH_CAVEAT, STYLE  # noqa: E402
from correction import CorrectionResult  # noqa: E402
from dialogue import LEVELS, SCENES, Utterance, opening_line, reply  # noqa: E402
from speech.voice import (  # noqa: E402
    SILENT_PEAK,
    SpeechError,
    loudest_sample,
    playback_seconds,
    speaking_seconds,
    synthesise,
    transcribe,
)

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


def warming_enabled() -> bool:
    """Whether to build the index at page load. Off makes it lazy again.

    THE ESCAPE HATCH IS FOR MEMORY, NOT FOR SPEED. Warming means the embedding model
    is loaded on every boot rather than only when a correction first needs it, so a
    deployment that used to survive by never touching it now loads several hundred
    megabytes at startup. If the free tier cannot hold that, `WARM_RETRIEVAL=0`
    returns to loading it on demand with an environment variable and no rebuild —
    the same door `CONTINUOUS_VOICE=0` opens for a venue whose network will not
    carry WebRTC.
    """
    return os.environ.get("WARM_RETRIEVAL", "1").strip().lower() not in {"0", "false", "no"}


@st.cache_resource(show_spinner=False)
def _warm_retrieval() -> threading.Thread | None:
    """Start building the index while the learner is still choosing a scene.

    THE FIRST CORRECTION PAYS FOR THE INDEX. Loading the embedding model and
    embedding 36 sections takes about 15 seconds, and it happened on whichever call
    asked for it first — so the first thing the learner ever waited for was the
    slowest thing the app does. Nothing about it needs the learner: the corpus is
    eight files that do not change. Starting it at page load spends that time
    against the setup screen, which is a screen someone is reading anyway.

    CACHED SO IT HAPPENS ONCE PER PROCESS. Streamlit re-runs this file top to
    bottom on every interaction; a thread started at module level would be a new
    thread on every click. `st.cache_resource` is the one thing here that is not
    re-run, so the thread is started inside it.

    AFTER set_page_config, NOT BEFORE. That call has to be the first Streamlit
    command in the script, and a cached function is entitled to draw a spinner —
    hence show_spinner=False as well, since there is nothing to wait for.

    NOTHING IT DOES CAN FAIL LOUDLY. A build without retrieval still corrects, just
    ungrounded, and the warm-up must not be the thing that turns that into an error
    on a page the learner has not touched yet. Nor may it call st.* : it is off the
    script's thread and has no context to draw into.
    """

    if not warming_enabled():
        return None

    def warm() -> None:
        with contextlib.suppress(Exception):
            from retrieval.index import collection

            collection()

    thread = threading.Thread(target=warm, name="warm-retrieval", daemon=True)
    thread.start()
    return thread


_warm_retrieval()

SESSION_KEYS = (
    "scene",
    "level",
    "history",
    "failure",
    "corrections",
    "caveat_seen",
    "used_speech",
    "spoken",
    "audio_cache",
    "unheard",
)

# One conversation's worth of replies, at roughly 90KB of WAV each. `max_turns()`
# defaults to 20, so the cap is the conversation rather than a guess.
MAX_CACHED_LINES: Final = 20


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
    # The opening line is marked read already, because it is not read: the scene's
    # greeting is on screen before anyone has said anything, and a page that starts
    # talking to a room by itself is not what this is.
    st.session_state["spoken"] = 0


def end_session() -> None:
    st.session_state["review"] = corrections()
    st.session_state["review_used_speech"] = bool(st.session_state.get("used_speech"))
    for key in SESSION_KEYS:
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

    st.divider()
    st.markdown(NOTICE)
    st.caption(f"Questions, or want your session stopped mid-way? {CONTACT}")


def render_conversation() -> None:
    scene: str = st.session_state["scene"]
    level: str = st.session_state["level"]

    st.title(SCENES[scene])
    st.caption(f"{LEVELS[level]} · write in Japanese · corrections come at the end")

    # The audio's place on the page, claimed in whichever bubble is last. It is
    # claimed here as well as in the reply block below because a reply written on an
    # earlier run is drawn by this loop, and that reply may still be owed its audio.
    audio_slot: Any | None = None

    for index, utterance in enumerate(history()):
        role = "user" if utterance.speaker == "learner" else "assistant"
        with st.chat_message(role):
            st.write(utterance.text)
            if utterance.speaker == "partner" and index == len(history()) - 1:
                audio_slot = st.empty()

    if unheard := st.session_state.pop("unheard", None):
        # Drawn here rather than where it was decided, because that run ended in a
        # rerun so that the microphone would be listening again by the time this is
        # read.
        st.warning(unheard)

    awaiting_reply = bool(history()) and history()[-1].speaker == "learner"
    failure: str | None = st.session_state.get("failure")

    # THE ORDER OF THIS FUNCTION IS THE FEATURE. Everything below is drawn in the
    # order the learner needs it, not the order it is produced in: the reply first,
    # then the box they type or speak into, then the sound, then the button that ends
    # the conversation — and last of all the loop that waits for them to talk, which
    # blocks until they do. Anything drawn after that loop is drawn after the turn is
    # already over, which means it is not drawn at all.
    if awaiting_reply and failure is None:
        with st.chat_message("assistant"):
            with st.spinner("…"):
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
            history().append(Utterance("partner", answer))
            st.write(answer)
            # The audio's place in this bubble, claimed now and filled in further
            # down. Reserving it is what lets the player sit under the reply it
            # belongs to while being produced after the input box exists.
            audio_slot = st.empty()

    if failure is not None:
        # A canned Japanese line here would read as a reply and teach the learner
        # something the model never said, so the failure is stated plainly instead.
        st.error(f"The reply could not be generated. {failure}")
        if st.button("Try again", type="primary"):
            st.session_state["failure"] = None
            st.rerun()

    listening: tuple[Any, Any] | None = None
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
        listening = render_input()

    # AFTER THE INPUT BOX, AND THAT IS WHAT MOVED. Synthesis takes about 4.3 seconds,
    # and it used to run before the input box was drawn — so the learner sat looking
    # at a reply they could not answer for the length of it. Drawn in this order the
    # box is on screen and usable while the audio is still being made.
    #
    # ASKED OF THE CONVERSATION, NOT OF THIS RUN. "Did I generate a reply just now"
    # is the wrong question and cost the audio entirely when it was asked on
    # 2026-08-22: the microphone widget triggers a rerun of its own while the four
    # seconds of synthesis are still running, the run producing the audio is thrown
    # away, and the next run has nothing to say because the reply is already in the
    # history. Recording which line has been read aloud makes the next run finish the
    # job instead — the same shape as `awaiting_reply` above, which is why a failed
    # reply is retried rather than lost.
    #
    # WHAT IT STILL COSTS, PLAINLY: send the next sentence while the audio is being
    # made and this turn's line is not read aloud, because the conversation has moved
    # on and reading it then would be reading the wrong line. Nothing becomes
    # unreadable — the reply is on screen as text.
    spoken_seconds = 0.0
    last = len(history()) - 1
    if audio_slot is not None and browser_voice_enabled():
        # The browser's own voice: no round trip, no rate limit, and nothing to wait
        # for. Drawn every run so the control stays pressable; spoken only the first
        # time, so a rerun does not read the same line again.
        first_time = st.session_state.get("spoken") != last
        spoken_seconds = _speak_in_browser(
            history()[last].text, audio_slot, announce=first_time
        )
        if first_time:
            st.session_state["spoken"] = last
        else:
            spoken_seconds = 0.0
    elif audio_slot is not None and st.session_state.get("spoken") != last and not tts_is_quiet():
        # THE COOL-DOWN IS CHECKED HERE RATHER THAN INSIDE speak(), so that a line
        # skipped without ever being attempted is not recorded as read. It changes
        # nothing the learner hears and everything the flag means: "spoken" has to
        # mean spoken, or nobody reading this later can rely on it for anything else.
        spoken_seconds = speak(history()[last].text, audio_slot)
        # After, never before: a run cancelled mid-synthesis has to leave the line
        # marked unspoken, or the retry this whole arrangement exists for never runs.
        # A synthesis that WAS tried and failed is marked — retrying a 429 on the
        # next rerun is how a rate limit gets worse rather than better.
        st.session_state["spoken"] = last

    st.divider()
    if st.button("End the conversation"):
        # READ FROM THE HISTORY, NOT FROM A RUNNING TALLY. Every learner line is in
        # there, including the ones whose reply failed — those used to go
        # uncorrected, because the old per-turn call sat in the branch that only
        # runs when a reply came back. The count on the review screen now matches
        # what the learner actually said.
        said = [utterance.text for utterance in history() if utterance.speaker == "learner"]
        if said:
            # BEFORE end_session(), which pops the scene and the level. The
            # correction needs both, and they are gone the moment it runs.
            noun = "sentence" if len(said) == 1 else "sentences"
            with st.spinner(f"Checking your {len(said)} {noun}…"):
                st.session_state["corrections"] = correct_all(said, scene, level)
        end_session()
        st.rerun()

    # LAST, BECAUSE IT BLOCKS. This waits for the learner to speak and then stop
    # speaking, and it returns straight into a rerun — so every line above it has
    # already reached the browser and nothing below it would.
    if listening is not None:
        context, status = listening
        heard_audio = continuous.collect_turn(context, status, skip_seconds=spoken_seconds)
        if heard_audio is not None:
            _send_recording(heard_audio)
        elif continuous.is_live(context):
            # THE PAGE HAS TO GO ROUND AGAIN, or it is finished. Returning here used
            # to end the script run with the stream still open and nothing left to
            # wake it: the microphone widget only reruns the page when its own state
            # changes, and a connected stream that has simply stopped delivering
            # frames changes nothing. The learner was left looking at "Listening…"
            # for ever, which is what happened on the deployed app on 2026-08-24.
            #
            # Only when the stream is up. When it is not, `collect_turn` returns
            # immediately, the record button is on screen instead, and rerunning here
            # would spin the page as fast as it could draw. With the stream up the
            # frame loop has already waited out its timeout, so this goes round about
            # once every few seconds.
            print("[listen] no turn collected; listening again", file=sys.stderr, flush=True)
            st.rerun()


def _audio_for(text: str) -> bytes:
    """The line as audio, made once per session however many times it is asked for.

    A RUN CANCELLED MID-SYNTHESIS IS A REQUEST ALREADY PAID FOR. The microphone
    widget reruns the script while the four seconds of synthesis are still going, and
    the next run synthesises the same sentence again — the first call still reached
    the provider, still cost its characters and still counted against a rate limit
    that turned out to be easy to reach (429s on 2026-08-22, from one person
    practising). Remembering the bytes makes the second attempt free instead.

    KEPT PER SESSION, NOT PER PROCESS. A module-level cache would be the obvious
    place and would also let one learner's reply be held in memory after they close
    the tab, and handed to whoever produces the same sentence next. This is the
    partner's words rather than the learner's, so it is a small thing — and this
    project's answer to small privacy questions is the same as its answer to large
    ones. It goes when the conversation goes, with the rest of SESSION_KEYS.
    """
    cache: dict[str, bytes] = st.session_state.setdefault("audio_cache", {})
    if text not in cache:
        # Counted only on a real call: a cache hit sends no characters anywhere.
        spend_tts_chars(text)
        made = synthesise(text)
        if len(cache) >= MAX_CACHED_LINES:
            cache.pop(next(iter(cache)))
        cache[text] = made
    return cache[text]


def browser_voice_enabled() -> bool:
    """Whether to let the browser read the reply, instead of sending for a recording.

    ON BY DEFAULT SINCE 2026-08-24, and the reason is arithmetic. Asking the provider
    for the audio costs 3.7 seconds on every turn and is refused outright once the
    free tier's limit is reached, which one person practising alone manages in a
    handful of turns. The browser's own voice starts immediately, cannot be rate
    limited, and cannot disappear when a preview model does.

    It was considered and rejected in the latency design on 2026-08-21 — "whether the
    venue's devices have a Japanese voice cannot be known from here" — and the facts
    that decided it have since changed. The path it lost to turns out to be silent
    quite often by itself, and slow when it is not.

    WHAT IT COSTS: the voice belongs to the device rather than to us, so it is more
    mechanical, and a device with no Japanese voice installed says nothing at all.
    `BROWSER_VOICE=0` restores the provider's voice exactly, with an environment
    variable and no rebuild.
    """
    return os.environ.get("BROWSER_VOICE", "1").strip().lower() not in {"0", "false", "no"}


def _speak_in_browser(text: str, slot: Any, *, announce: bool) -> float:
    """Have the page say the line itself. Returns roughly how long it will take.

    DRAWN ON EVERY RUN, SPOKEN ON ONE. The control has to survive a rerun or it is not
    a control: the page goes round every few seconds while the microphone listens, and
    a button that exists only on the run that produced the reply is gone before anyone
    could press it. `announce` is what separates the two — false redraws the button
    and stays quiet, so nobody gets the same sentence read to them twice.

    A CONTROL AS WELL AS AN ATTEMPT, for the reason the provider's player has one:
    iOS Safari will not start audio without a gesture on the same rendering of the
    page, and a reply arrives on a later rerun than the tap that asked for it. So it
    tries, and there is something to press where trying is not allowed.

    The voice list loads asynchronously in some browsers, which is why this waits for
    `voiceschanged` when it arrives empty rather than concluding there is no voice.
    """
    # THE LINE IS A LANGUAGE MODEL'S OUTPUT AND THIS IS AN IFRAME WITH SAME-ORIGIN
    # ACCESS, which st.iframe's own documentation warns about by name. `json.dumps`
    # makes a safe JavaScript string literal for quotes and backslashes but leaves
    # `</script>` intact, and that alone closes the block and starts running markup.
    # Escaping the slash is the standard answer and keeps the literal valid.
    spoken = json.dumps(text).replace("</", "<\\/")
    # Into the slot claimed in the reply's bubble, not wherever the script happens to
    # be — which by this point is below the input box.
    with slot:
        st.iframe(
            f"""
            <div style="font:14px/1.5 Georgia,serif;color:#5b5347">
              <button id="again" style="font:inherit;border:1px solid #cfc6b6;background:#f2ece1;
                color:#1c1a17;border-radius:4px;padding:2px 10px;cursor:pointer">▶ もう一度</button>
              <span id="note"></span>
            </div>
            <script>
            const line = {spoken};
            function japanese() {{
              return (window.speechSynthesis.getVoices() || [])
                .find(v => v.lang && v.lang.toLowerCase().startsWith("ja"));
            }}
            function say() {{
              const voice = japanese();
              if (!voice) {{
                document.getElementById("note").textContent =
                  " この端末には日本語の音声が入っていません。";
                return;
              }}
              const said = new SpeechSynthesisUtterance(line);
              said.voice = voice;
              said.lang = "ja-JP";
              window.speechSynthesis.cancel();
              window.speechSynthesis.speak(said);
            }}
            document.getElementById("again").onclick = say;
            if ({"true" if announce else "false"}) {{
              if ((window.speechSynthesis.getVoices() || []).length === 0) {{
                window.speechSynthesis.onvoiceschanged = () => {{
                  window.speechSynthesis.onvoiceschanged = null;
                  say();
                }};
              }} else {{
                say();
              }}
            }}
            </script>
            """,
            height=34,
        )
    # An estimate, because nothing reports back from in there. See speaking_seconds.
    return speaking_seconds(text)


def _no_audio(text: str, exc: Exception) -> None:
    """Say why the line was not read aloud, where only the operator will see it."""
    print(f"[speak] no audio for {text!r}: {exc}", file=sys.stderr, flush=True)


def speak(text: str, slot: Any) -> float:
    """Read one line aloud, into a place already claimed on the page.

    Returns how long the clip plays for, which the listener needs in order to throw
    away the frames in which the app can be heard talking. Zero when nothing plays,
    which correctly turns that discard off.

    A failure here is silence, not an error: the reply is already on screen and the
    conversation can continue without sound. Losing the audio is a smaller problem
    than an error box where a reply should be — and, since 2026-08-22, smaller than a
    line of provider English under a beginner's first sentence in Japanese.
    """
    # BOTH CLAUSES END THE SAME WAY, AND THAT IS THE POINT: SILENT TO THE LEARNER,
    # LOUD IN THE LOG. The error used to be printed under the reply, where it was a
    # line of English a beginner can do nothing about — "answered 429 Too Many
    # Requests" is not a thing to hand someone practising 「おはようございます」.
    # Whoever is running the demo does need it, so it goes to stderr, which is where
    # the host keeps its logs.
    try:
        audio = _audio_for(text)
    except SpeechError as exc:
        if exc.status == 429:
            # Everyone at a meetup shares one key, so this quiets every tab this
            # process is serving, not just the one that asked.
            start_tts_cooldown()
        _no_audio(text, exc)
        return 0.0
    except Exception as exc:  # noqa: BLE001 - see below
        # Deliberately broad. The reply is already on screen and the conversation can
        # continue without sound, so NOTHING that happens while reading a line aloud
        # may end the session. A 4xx escaped a narrower clause here on 2026-08-21 and
        # took the whole page down mid-conversation.
        _no_audio(text, exc)
        return 0.0
    # AUTOPLAY AND A CONTROL, because neither alone works everywhere. Hiding the
    # player entirely was tried on 2026-08-21: it plays on a laptop and is silent on
    # an iPhone, where Safari refuses to autoplay audio and the learner is left with
    # no way to hear the line at all. Streamlit's own player is the other extreme — a
    # scrub bar, a duration and an overflow menu around two seconds of speech.
    #
    # So: it plays by itself where the browser allows it, and where it does not there
    # is something to press. The CSS keeps it to the size of a button.
    encoded = base64.b64encode(audio).decode()
    slot.markdown(
        f'<audio class="reply-audio" controls autoplay>'
        f'<source src="data:audio/wav;base64,{encoded}" type="audio/wav"></audio>',
        unsafe_allow_html=True,
    )
    return playback_seconds(audio)


def _unheard(message: str, reason: str) -> None:
    """Tell the learner the turn did not land, and start listening again.

    THE RERUN IS THE POINT. Saying so and returning left the script at the end of its
    run with nothing listening — the microphone loop is the last statement of
    `render_conversation`, so returning past it means the page is done. The learner
    carried on talking into a page that had stopped paying attention, which is what
    "no change" looks like from their side. The message goes through session state
    because a rerun throws away whatever the current run has drawn.
    """
    st.session_state["unheard"] = message
    print(f"[listen] {reason}", file=sys.stderr, flush=True)
    st.rerun()


def _send_recording(audio: bytes) -> None:
    """Transcribe one turn's audio and put it in the conversation.

    Shared by both input paths, so the continuous stream and the button reach the
    correction engine by exactly the same route.
    """
    seconds = playback_seconds(audio)
    peak = loudest_sample(audio)

    if peak < SILENT_PEAK:
        # DECIDED HERE, NOT BY THE MODEL, because the model does not decide it the way
        # anyone would expect. Asked on 2026-08-24 to transcribe two seconds of
        # digital silence — with a prompt that says "if there is no speech, output
        # nothing at all" — it answered 「はい」. Three times, on three different silent
        # inputs. Sent on, that becomes a sentence the learner never said, attributed
        # to them in the conversation and then corrected. This app has exactly one
        # thing it must not do, and inventing learner speech is it.
        _unheard(
            "Nothing was heard. Please try again — a little closer to the microphone.",
            f"silent recording: {seconds:.1f}s, peak {peak:.4f}",
        )

    with st.spinner("…"):
        try:
            heard = transcribe(audio)
        except SpeechError as exc:
            # The provider failing is not the learner failing, and the message no
            # longer says it is.
            _unheard(
                "That did not come through. Please say it again.",
                f"transcription failed on {seconds:.1f}s at peak {peak:.2f}: {exc}",
            )
        except Exception as exc:  # noqa: BLE001 - a failed recording is not a crash
            _unheard(
                "That did not come through. Please say it again.",
                f"transcription error on {seconds:.1f}s at peak {peak:.2f}: "
                f"{type(exc).__name__}: {exc}",
            )
    if not heard:
        _unheard(
            "Nothing was heard. Please try again.",
            f"empty transcription of {seconds:.1f}s at peak {peak:.2f}",
        )
    history().append(Utterance("learner", heard))
    st.session_state["used_speech"] = True
    st.session_state["failure"] = None
    st.rerun()


def render_input() -> tuple[Any, Any] | None:
    """Draw the input box. Returns the open microphone, for the caller to collect from.

    NOTHING HERE WAITS. It used to: the continuous listener drew its widget and then
    blocked in the same call until the learner had spoken, so the reply's audio and
    the button that ends the conversation — both written below this call — were never
    reached on any turn where the microphone connected. The stream is opened here and
    the waiting is done by the caller, last, once the page is complete.

    The returned pair is the stream context and the container the status line belongs
    in. The container is made here because that is where it appears on the page; it is
    written into later, from a call sitting much further down the file.

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

    if continuous.enabled():
        # The microphone stays open and silence ends the turn.
        #
        # AND THE BUTTON IS THERE WHENEVER IT IS NOT. This comment used to say the
        # screen "falls through to the button if the stream never connects" and the
        # code returned before reaching it, so a learner whose WebRTC did not connect
        # got "Starting the microphone…" and no way to speak at all — which is what
        # happened on the deployed app on 2026-08-24. WebRTC needs STUN and often
        # TURN, this app has the first and not the second, and a hall in Bangalore on
        # 13 September is exactly where that runs out. A promise in a comment is not a
        # fallback.
        status = st.container()
        context = continuous.open_stream()
        if not continuous.is_live(context):
            _offer_the_button()
        if typed := st.chat_input("または、日本語で書いてください"):
            history().append(Utterance("learner", typed))
            st.session_state["failure"] = None
            st.rerun()
        return context, status

    _offer_the_button()

    if typed := st.chat_input("または、日本語で書いてください"):
        history().append(Utterance("learner", typed))
        st.session_state["failure"] = None
        st.rerun()
    # The button path has nothing to collect later: `st.audio_input` hands back a
    # finished recording rather than a stream, so it never blocked in the first place.
    return None


def _offer_the_button() -> None:
    """Press to record one turn. The path that needs nothing but HTTP.

    A KEY THAT CHANGES EVERY TURN. Without it the widget hands back the same
    recording after the rerun, the same sentence is transcribed and sent again, and
    the conversation runs away on its own — three identical turns appeared on the
    deployed app on 2026-08-21 before anyone touched the microphone a second time.
    """
    recording = st.audio_input("話してください", key=f"microphone-{len(history())}")
    if recording is not None:
        _send_recording(recording.getvalue())


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
        # Written as one block of HTML rather than assembled from widgets, so that the
        # colour belongs to the card. EVERY PIECE IS ESCAPED: three of these four
        # strings came out of a language model, and one of them is echoed back from
        # whatever the learner said.
        said = escape(result.learner_sentence)
        if not answer.needs_correction:
            st.markdown(
                f'<div class="review-card ok">'
                f'<div class="review-said">{said}</div>'
                f'<div class="review-ok-line">This one is fine as it is.</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
            continue

        why = ""
        if answer.reason_en:
            why = f'<div class="review-why">{escape(answer.reason_en)}</div>' 
        source = ""
        if answer.grounding_ids:
            cited = ", ".join(escape(one) for one in answer.grounding_ids)
            source = f'<div class="review-source">Reference: {cited}</div>'
        st.markdown(
            f'<div class="review-card fixed">'
            f'<div class="review-said">{said}</div>'
            f'<div class="review-fixed-line">→ {escape(answer.corrected_sentence or "")}</div>'
            f"{why}{source}"
            f"</div>",
            unsafe_allow_html=True,
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
