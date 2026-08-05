"""The correction.

A separate call from the conversation, run once per learner sentence. It is never
shown while the learner is talking: interrupting a beginner mid-conversation is the
fastest way to make them stop, and the conversation partner is explicitly forbidden
from repairing their Japanese, so this is the only place a correction is produced.

The output is parsed here rather than handed to a provider's constrained-decoding
mode on purpose. `format_compliance_rate` is one of the three numbers week 1 has to
produce, and it only means something if a broken output is actually observable.
Constrained decoding would make the JSON half of that metric true by construction
while leaving the other half — a reason that comes back in Japanese — unmeasured,
which is precisely the failure documented in docs/ja/glossary.md §5.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Final, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from dialogue.scenes import level_brief, scene_brief
from llm import as_text, build_chat_model

# Recorded in every run record. Bump it whenever the wording below changes, or
# measurements taken weeks apart stop being comparable.
PROMPT_VERSION: Final = "correction-v1"

# The conversation wants variety; the judgement must not have any. The same
# sentence measured twice has to give the same label, or the evaluation numbers
# move on their own between runs.
TEMPERATURE: Final = 0.0

# One retry, as fixed in docs/ja/functional-design.md. More would hide a model that
# cannot hold the format at all, which is the thing the metric exists to expose.
MAX_ATTEMPTS: Final = 2

FormatProblem = Literal["invalid_json", "reason_not_english"]


@dataclass(frozen=True)
class Correction:
    """One judgement about one learner sentence.

    Keys match docs/ja/functional-design.md exactly, including `grounding_ids`,
    which stays empty until retrieval arrives in week 2. It is carried from the
    start so that adding it later does not invalidate data already written.
    """

    needs_correction: bool
    corrected_sentence: str | None
    reason_en: str | None
    grounding_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CorrectionResult:
    """What one call produced, plus what the format metric needs to count it.

    `format_problems` describes the FIRST attempt, even when a retry succeeded. A
    retry that quietly repaired the output would otherwise make
    `format_compliance_rate` report a model that never breaks the format, which is
    the same lie as dropping the broken cases from the denominator.
    """

    learner_sentence: str
    correction: Correction | None
    attempts: int
    format_problems: tuple[FormatProblem, ...]

    @property
    def format_compliant(self) -> bool:
        return not self.format_problems


class CorrectionFormatError(ValueError):
    """The model's output was not the JSON object the prompt asked for."""


SYSTEM_PROMPT: Final = """\
You judge one sentence written by someone learning Japanese, and you answer with \
JSON. You are not talking to the learner.

The situation they are in: {situation}
Their level: {level}

Decide whether the sentence should be changed before they say it to a Japanese \
speaker in that situation.

It needs correction when:
- it is grammatically wrong — a wrong particle, a wrong conjugation, a missing \
required element
- the politeness does not fit the situation
- it is grammatical but no Japanese speaker would put it that way, including \
word-for-word translations from English
- it is a fixed expression that has been altered

It does NOT need correction when:
- it is simple but correct. A beginner's sentence is not wrong for being plain
- it is casual or regional but genuinely used
- a Japanese speaker would not stop at it, even if you would personally choose \
another wording

WHEN YOU ARE UNSURE, SAY IT DOES NOT NEED CORRECTION. Changing a sentence that was \
already fine is the more damaging mistake here: it teaches the learner that correct \
Japanese was wrong, and it makes them doubt every sentence they got right.

Do not judge pronunciation. Do not classify the type of error.

Answer with exactly this JSON object and nothing else — no markdown fence, no \
commentary before or after:

{{"needs_correction": true or false,
  "corrected_sentence": "the natural way to say it, in Japanese" or null,
  "reason_en": "one or two sentences of English" or null,
  "grounding_ids": []}}

- `corrected_sentence` and `reason_en` are null when `needs_correction` is false.
- `corrected_sentence` changes as little as possible. Repair the sentence they \
wrote; do not write a better sentence of your own.
- `reason_en` IS WRITTEN IN ENGLISH. Quote Japanese inside 「」 when you need to \
point at a word, but the explanation itself is English — the learner reads English, \
not Japanese.
- `grounding_ids` is always an empty array.
"""

_REPAIR_PROMPT: Final = """\
That answer was not usable: {problem}. Answer again with the JSON object only — no \
prose, no markdown fence — with exactly the keys needs_correction, \
corrected_sentence, reason_en and grounding_ids.
"""

# From the first "{" to the last "}", so a fence or a stray sentence around the
# object does not fail the parse. Two separate objects in one answer would, and
# that is fine: that answer did not follow the format.
_JSON_OBJECT: Final = re.compile(r"\{.*\}", re.DOTALL)

# Kana and kanji. The bracket characters 「」 are punctuation and deliberately not
# in these ranges, so a quoted Japanese word inside an English reason is allowed.
_JAPANESE: Final = re.compile(r"[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]")

_QUOTED: Final = re.compile(r"「[^」]*」|\"[^\"]*\"|'[^']*'|“[^”]*”")


def check(sentence: str, scene: str, level: str) -> CorrectionResult:
    """Judge one learner sentence.

    Provider errors propagate. A broken answer does not: it is a measurable outcome
    rather than a fault, so it comes back as a result with no correction in it.
    """
    role, _ = scene_brief(scene)
    model = build_chat_model(temperature=TEMPERATURE)
    messages: list[BaseMessage] = [
        SystemMessage(SYSTEM_PROMPT.format(situation=role, level=level_brief(level))),
        HumanMessage(sentence),
    ]

    # Only the first attempt is described here; see CorrectionResult.
    first_problems: tuple[FormatProblem, ...] = ()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        answer = as_text(model.invoke(messages).content)
        try:
            correction = parse_correction(answer)
        except CorrectionFormatError as exc:
            if attempt == 1:
                first_problems = ("invalid_json",)
            if attempt == MAX_ATTEMPTS:
                return CorrectionResult(sentence, None, attempt, first_problems)
            # Sending the same prompt again at temperature 0 would produce the same
            # broken answer, so the retry has to say what was wrong with it.
            messages += [AIMessage(answer), HumanMessage(_REPAIR_PROMPT.format(problem=exc))]
            continue

        if attempt == 1:
            first_problems = _format_problems(correction)
        return CorrectionResult(sentence, correction, attempt, first_problems)

    raise AssertionError("the loop above always returns")


def parse_correction(answer: str) -> Correction:
    """Turn one model answer into a `Correction`, or say why it cannot be one."""
    match = _JSON_OBJECT.search(answer)
    if match is None:
        raise CorrectionFormatError("there was no JSON object in it")

    try:
        payload = json.loads(match.group())
    except json.JSONDecodeError as exc:
        raise CorrectionFormatError(f"the JSON did not parse ({exc.msg})") from exc

    if not isinstance(payload, dict):
        raise CorrectionFormatError("the JSON was not an object")

    needs_correction = payload.get("needs_correction")
    if not isinstance(needs_correction, bool):
        raise CorrectionFormatError("needs_correction was not true or false")

    corrected_sentence = _optional_text(payload.get("corrected_sentence"))
    reason_en = _optional_text(payload.get("reason_en"))

    if needs_correction and (corrected_sentence is None or reason_en is None):
        raise CorrectionFormatError(
            "needs_correction was true without both corrected_sentence and reason_en"
        )
    if not needs_correction:
        # A sentence that was already fine has nothing to show, whatever the model
        # decided to put in these two fields.
        corrected_sentence = None
        reason_en = None

    return Correction(
        needs_correction=needs_correction,
        corrected_sentence=corrected_sentence,
        reason_en=reason_en,
        grounding_ids=_grounding_ids(payload.get("grounding_ids")),
    )


def reason_is_english(reason: str) -> bool:
    """Whether the explanation itself is in English.

    Quoted Japanese is expected — pointing at 「は」 is how you explain a particle —
    so quotes are removed before looking for Japanese. Anything left is the model
    explaining in the wrong language, which docs/ja/glossary.md §5 counts as a
    format failure rather than a wrong judgement.
    """
    outside_quotes = _QUOTED.sub(" ", reason)
    if _JAPANESE.search(outside_quotes):
        return False
    return bool(re.search(r"[A-Za-z]", outside_quotes))


def _format_problems(correction: Correction) -> tuple[FormatProblem, ...]:
    if correction.reason_en is not None and not reason_is_english(correction.reason_en):
        return ("reason_not_english",)
    return ()


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _grounding_ids(value: Any) -> tuple[str, ...]:
    # Week 1 asks for an empty array and gets one. Whatever arrives is kept rather
    # than rejected: retrieval fills this in week 2, and an answer that guessed an
    # id early is not a broken answer.
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, str))
    return ()
