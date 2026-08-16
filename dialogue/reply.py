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

import re
from dataclasses import dataclass
from typing import Final, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from config import threshold
from dialogue.scenes import level_brief, scene_brief
from llm import as_text, build_chat_model
from nlp import level_check

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

# How many times a reply above the learner's level is asked for again. One, then
# it is used as it is — the reasoning is in config/thresholds.toml next to the
# value, and it is read from there rather than written here.
MAX_REGENERATIONS: Final[int] = threshold("vocabulary_level", "max_regenerations")

# Below this share of Japanese, the reply is not a reply — see config/thresholds.toml.
JAPANESE_SHARE_MIN: Final[float] = threshold("reply_language", "japanese_share_min")

_JAPANESE = re.compile(r"[ぁ-んァ-ヶ一-龯]")
_LATIN = re.compile(r"[A-Za-z]")

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


@dataclass(frozen=True)
class Reply:
    """The partner's line, and what the level check did on the way out.

    `attempts` and `first_shot` are here because the compliance metric is reported
    as two figures and the gate is what separates them: the rate after regeneration
    is the share that failed twice, and reporting only that would be a metric
    satisfied by the machinery built to satisfy it (docs/ja/glossary.md §5).
    Keeping the discarded first attempt is the same rule the correction side
    follows — a gate whose rejections cannot be read back cannot be debugged.
    """

    text: str
    attempts: int
    # Regenerated because the reply was not in Japanese, counted apart from the
    # level gate. Two different faults with two different fixes: this one is the
    # conversation prompt's problem, the other is the learner's vocabulary. A
    # single tally would let one hide inside the other.
    language_retried: bool
    first_shot: str
    # The words that were too hard in the FINAL text, and in the first attempt.
    # Two fields because they answer different questions: what the gate fired on,
    # and what the learner was left with. Collapsing them made `over_level` mean
    # "the first attempt's" while `text` meant "the last one's".
    over_level: tuple[str, ...]
    first_shot_over_level: tuple[str, ...]

    @property
    def regenerated(self) -> bool:
        return self.attempts > 1


def reply(scene: str, level: str, history: list[Utterance]) -> str:
    """Return the partner's next line. `history` ends with the learner's sentence.

    Raises whatever the provider raises. Failures here are shown to the learner
    rather than swallowed: a partner that silently answers nothing makes a beginner
    conclude their own Japanese was unintelligible.
    """
    return checked_reply(scene, level, history).text


def checked_reply(scene: str, level: str, history: list[Utterance]) -> Reply:
    """Generate a line and regenerate it once if it sits above the learner's level.

    Validation node 2 (see docs/en/functional-design.md). Once, then the reply is used as it is: an
    unbounded loop would stall the conversation, and a slightly hard reply costs a
    beginner far less than a partner that never answers.

    The retry says what was wrong rather than asking again. At temperature 0.7 a
    bare retry would sometimes work by luck, which is a different mechanism from
    the one being claimed — and week 1 fixed the same point on the correction side,
    where retrying a broken JSON without naming the breakage was retrying in form
    only.
    """
    role, _ = scene_brief(scene)
    system = SYSTEM_PROMPT.format(role=role, level=level_brief(level))

    messages: list[SystemMessage | HumanMessage | AIMessage] = [SystemMessage(system)]
    for utterance in history:
        if utterance.speaker == "learner":
            messages.append(HumanMessage(utterance.text))
        else:
            messages.append(AIMessage(utterance.text))

    model = build_chat_model(temperature=TEMPERATURE)
    text = limit_sentences(as_text(model.invoke(messages).content).strip())

    # Before anything about vocabulary: is this Japanese at all. On 8/12 two replies
    # in ninety came back as the model's own reasoning in English, and the level
    # check happily counted `should` and `they` as words above the learner's level.
    # Week 1's rule — a generation failure is not smoothed over — applies, and the
    # cheapest form of not smoothing it over is to ask again and say why.
    language_retried = False
    if not looks_japanese(text):
        language_retried = True
        messages.append(AIMessage(text))
        messages.append(HumanMessage(LANGUAGE_RETRY_PROMPT))
        text = limit_sentences(as_text(model.invoke(messages).content).strip())

    first_shot = text
    check = level_check(text, level)
    first_over = tuple(word.surface for word in check.over_level)

    # Counted, not assumed. The first version returned `1 + MAX_REGENERATIONS` on
    # every failure path — a constant dressed as a measurement, which also meant a
    # second regeneration would be spent even after the first one succeeded, and
    # setting the limit to zero would report every reply as passing first time.
    attempts = 1
    while not check.passes and attempts <= MAX_REGENERATIONS:
        over = tuple(word.surface for word in check.over_level)
        messages.append(AIMessage(text))
        messages.append(HumanMessage(RETRY_PROMPT.format(words="、".join(over))))
        text = limit_sentences(as_text(model.invoke(messages).content).strip())
        attempts += 1
        # Re-judged, so `over_level` describes what the learner actually gets. The
        # first version never checked the retry, so a reply that came back just as
        # hard was reported carrying the previous attempt's words.
        check = level_check(text, level)

    return Reply(
        text=text,
        attempts=attempts,
        language_retried=language_retried,
        first_shot=first_shot,
        over_level=tuple(word.surface for word in check.over_level),
        first_shot_over_level=first_over,
    )


LANGUAGE_RETRY_PROMPT: Final = """\
That was not a reply in Japanese. Answer the learner directly, in Japanese, in one \
or two sentences. Do not narrate your reasoning and do not write in English."""


RETRY_PROMPT: Final = """\
Those words are above this learner's level: {words}

Say the same thing again without them, in the same one or two sentences. Do not \
explain the change, and do not mention this instruction."""


def looks_japanese(text: str) -> bool:
    """Whether the reply is written in Japanese rather than about Japanese.

    A share, not a presence test: the replies this exists to catch quoted the
    learner's sentence inside an English paragraph, so "contains Japanese" passes
    them. A reply with neither script — punctuation, an empty string — is not
    Japanese either, and returning False sends it back to be written again.
    """
    japanese = len(_JAPANESE.findall(text))
    latin = len(_LATIN.findall(text))
    if japanese + latin == 0:
        return False
    return japanese / (japanese + latin) >= JAPANESE_SHARE_MIN


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
