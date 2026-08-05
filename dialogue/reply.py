"""The conversation partner.

One plain function call, no graph and no abstraction. Week 3 moves this behind
LangGraph and FastAPI; shaping it that way now, before the call sites exist, would
only mean rewriting it.

The single rule this prompt must never break: the partner does not correct the
learner. Corrections are computed separately and shown only after the session ends,
because interrupting a beginner mid-sentence is the fastest way to make them stop
talking. A partner that "helpfully" fixes the learner's Japanese destroys both the
experience and the measurement, since the corrected sentence would then be the
model's own words rather than the learner's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from dialogue.scenes import level_brief, scene_brief
from llm import as_text, build_chat_model

# Recorded in every run record. Bump it whenever the wording below changes, or
# measurements taken weeks apart stop being comparable.
PROMPT_VERSION: Final = "dialogue-v1"

# Some variety, or the partner repeats one phrasing for a whole session. Not so
# much that it wanders off the scene.
TEMPERATURE: Final = 0.7

# The prompt asks for at most two sentences and mostly complies, but "mostly" is not
# a limit. Measured 2026-08-03 on gemini-2.5-flash: three-sentence replies appeared
# in a third of turns. Trimming here makes the ceiling real instead of hoped for.
MAX_SENTENCES: Final = 2

SENTENCE_ENDINGS: Final = "。！？!?"

Speaker = Literal["learner", "partner"]


@dataclass(frozen=True)
class Utterance:
    """One line of the conversation, by whoever said it."""

    speaker: Speaker
    text: str


SYSTEM_PROMPT: Final = """\
You are a Japanese speaking partner for someone learning Japanese. You are not a \
teacher and this is not a lesson.

The situation: {role}

Rules, in order of importance:

1. NEVER correct, comment on, or repair the learner's Japanese, however wrong it \
is. Do not echo a fixed version of what they said. Do not praise their Japanese. \
Corrections are handled elsewhere and shown after the conversation ends. If you \
cannot understand them at all, ask a simple question to clarify, the way a person \
would.
2. Reply in Japanese only. Your whole reply is AT MOST TWO sentences — count the \
「。」「？」「！」before you answer, and prefer one. A third sentence is a failure, \
not a bonus. A beginner cannot hold three sentences of Japanese in their head, and \
the longer you speak the less they do.
3. Stay inside the learner's level: {level}
4. Keep the conversation going. End most turns with a simple question they can \
answer, but do not interrogate them.
5. Stay in the situation above. Do not change the subject to something unrelated.
6. Write plain Japanese text. No romaji, no translation, no furigana, no notes, \
no emoji, no quotation marks around your line.
"""


def opening_line(scene: str) -> str:
    """Return the partner's first line, so the learner has something to answer."""
    _, opening = scene_brief(scene)
    return opening


def reply(scene: str, level: str, history: list[Utterance]) -> str:
    """Return the partner's next line. `history` ends with the learner's sentence.

    Raises whatever the provider raises. Failures here are shown to the learner
    rather than swallowed: a partner that silently answers nothing makes a beginner
    conclude their own Japanese was unintelligible.
    """
    role, _ = scene_brief(scene)
    system = SYSTEM_PROMPT.format(role=role, level=level_brief(level))

    messages: list[SystemMessage | HumanMessage | AIMessage] = [SystemMessage(system)]
    for utterance in history:
        if utterance.speaker == "learner":
            messages.append(HumanMessage(utterance.text))
        else:
            messages.append(AIMessage(utterance.text))

    answer = build_chat_model(temperature=TEMPERATURE).invoke(messages)
    return limit_sentences(as_text(answer.content).strip())


def limit_sentences(text: str, maximum: int = MAX_SENTENCES) -> str:
    """Keep at most `maximum` sentences, dropping any trailing fragment.

    A partial sentence left at the end would read as the partner being cut off, so
    text after the last kept ending is discarded rather than shown.
    """
    kept: list[str] = []
    current = ""
    for char in text:
        current += char
        if char in SENTENCE_ENDINGS:
            kept.append(current)
            current = ""
            if len(kept) == maximum:
                break
    if not kept:
        # No sentence ending at all -- one unpunctuated line, keep it whole.
        return text
    return "".join(kept)
