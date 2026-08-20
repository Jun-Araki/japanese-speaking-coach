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
from dataclasses import dataclass, replace
from typing import Any, Final, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from config import threshold
from dialogue.scenes import level_brief, scene_brief
from llm import as_text, build_chat_model

# Recorded in every run record. Bump it whenever the wording below changes, or
# measurements taken weeks apart stop being comparable.
#
# v2 (2026-08-19, improvement cycle 1): one line added to the "does NOT need
# correction" list, saying that a politer or more idiomatic alternative is an
# upgrade rather than a correction. Chosen because over_correction_rate was the
# only published metric outside its target — 25.0% against a ceiling of 15% — and
# because three of the four remaining over-corrections were exactly that move: an
# honorific prefix added, a pronoun the speaker chose removed. Written as a general
# rule and not as a list of the sentences it was found on: a rule built from an
# item is a rule that answers that item.
PROMPT_VERSION: Final = "correction-v2"

# The grounded prompt is a SECOND version, not a replacement. Stage 0 of the
# comparison table is measured on the prompt above and has to stay reproducible
# after this file learns to retrieve, so the two versions live side by side and a
# run record says which one produced it.
GROUNDED_PROMPT_VERSION: Final = "correction-rag-v2"

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
- a more polite or more idiomatic version exists and what they wrote is still \
acceptable. Adding an honorific prefix, reaching for a set phrase, or removing a \
word the speaker chose is an UPGRADE, not a correction. Only correct what is wrong

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

# Appended to the prompt above when retrieval is on, replacing the last bullet. The
# articles are handed over whole — the sections the search returned, with their ids —
# because a citation the model never read is not grounding, it is decoration. Asking
# it to name the ones it USED, rather than recording what was shown, is what makes
# `grounding_ids` mean something: with score_min at 0 every search returns three
# sections whether or not any of them applies, so the model's choice is the only
# signal left about whether anything actually grounded the correction.
_GROUNDING_BLOCK: Final = """\

REFERENCE ARTICLES. These were retrieved for this sentence. They may or may not be \
relevant — judge that yourself.

{articles}

- `grounding_ids` lists the ids of the articles above that you ACTUALLY USED to \
decide. Use an empty array if none of them applies. Do not cite an article you did \
not use, and do not invent an id that is not listed above.
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

# How much Japanese may remain outside the quotes before the reason stops being an
# English explanation. See config/thresholds.toml for the measurements behind it.
_JAPANESE_RATIO_MAX: Final[float] = threshold("reason_language", "japanese_ratio_max")


def check(sentence: str, scene: str, level: str) -> CorrectionResult:
    """Judge one learner sentence.

    Provider errors propagate. A broken answer does not: it is a measurable outcome
    rather than a fault, so it comes back as a result with no correction in it.
    """
    return _judge(sentence, scene, level, grounding=None)


def check_with_retrieval(sentence: str, scene: str, level: str) -> CorrectionResult:
    """The same judgement, with the retrieved sections in front of the model.

    Retrieval is imported here rather than at module scope on purpose. It pulls in
    several hundred megabytes of embedding model, and the published build may have
    to run without it (the free tier may not take torch, in which case the deployed
    app drops retrieval and the measurements go on running locally). An import at
    the top would make that fallback impossible: the correction engine would refuse
    to load at all.

    A retrieval failure is not a correction failure. If the index cannot be built,
    the sentence is still judged — ungrounded, with `grounding_ids` empty, which is
    exactly what "nothing could be cited" is supposed to mean.
    """
    try:
        from retrieval.index import search

        results = search(sentence, scene=scene)
        block = "\n\n".join(
            f"[{result.article_id}] {result.heading}\n{result.body}" for result in results
        )
        allowed = {result.article_id for result in results}
    except Exception:  # noqa: BLE001 - any retrieval failure degrades to ungrounded
        block, allowed = "", set()

    return _judge(sentence, scene, level, grounding=(block, allowed))


def _judge(
    sentence: str,
    scene: str,
    level: str,
    grounding: tuple[str, set[str]] | None,
) -> CorrectionResult:
    role, _ = scene_brief(scene)
    prompt = SYSTEM_PROMPT.format(situation=role, level=level_brief(level))
    if grounding is not None and grounding[0]:
        prompt += _GROUNDING_BLOCK.format(articles=grounding[0])

    model = build_chat_model(temperature=TEMPERATURE)
    messages: list[BaseMessage] = [SystemMessage(prompt), HumanMessage(sentence)]

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
            first_problems = format_problems(correction)
        # An id the model made up is not grounding. Without this, a hallucinated
        # `grammar-009` would reach the learner as a citation and reach check 3 as
        # evidence that something was found.
        if grounding is not None:
            correction = replace(
                correction,
                grounding_ids=tuple(
                    one for one in correction.grounding_ids if one in grounding[1]
                ),
            )
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
    so quotes are removed first. What is left is judged by proportion rather than
    by presence: an English sentence that names a Japanese word inline ("the
    masu-stem of the verb (遅れ)") is in English, and counting it as a language
    failure would report a model as answering in Japanese when it never did. A
    reason genuinely written in Japanese has almost no Latin letters and fails.

    The threshold and the measurements behind it are in config/thresholds.toml.
    """
    # The no-Latin case is answered before the ratio, not by it. A reason with no
    # Latin letters and no Japanese either — digits, punctuation, an empty gesture —
    # scores a ratio of zero and would pass as English on a technicality.
    outside_quotes = _QUOTED.sub(" ", reason)
    if len(re.findall(r"[A-Za-z]", outside_quotes)) == 0:
        return False
    return japanese_ratio(reason) <= _JAPANESE_RATIO_MAX


def japanese_ratio(reason: str) -> float:
    """The proportion `reason_is_english` compares against the threshold.

    Recorded per item on `dev` runs so the threshold can be re-examined without
    re-measuring. glossary §7 asks for 0.25 to be reconfirmed against dev in week 2,
    and a boolean cannot answer that question: it says an item passed, not by how
    much. The day-4 rule was replaced precisely because nobody could see that the
    nine "failures" sat nowhere near a reason actually written in Japanese.
    """
    outside_quotes = _QUOTED.sub(" ", reason)
    japanese = len(_JAPANESE.findall(outside_quotes))
    latin = len(re.findall(r"[A-Za-z]", outside_quotes))
    if japanese + latin == 0:
        return 0.0
    return japanese / (japanese + latin)


def japanese_left_unquoted(reason: str) -> bool:
    """Whether any Japanese sits outside quotes, however little.

    Not a format failure — see reason_is_english — but recorded per item in the run
    record, because the correction prompt asks for 「」 and the baseline prompt does
    not, and that difference should be visible rather than inferred.
    """
    return bool(_JAPANESE.search(_QUOTED.sub(" ", reason)))


def format_problems(correction: Correction) -> tuple[FormatProblem, ...]:
    """What is wrong with the FORM of a parsed correction, if anything.

    Shared with the baseline so that both sides of the comparison table have their
    format compliance judged by the same code.
    """
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
