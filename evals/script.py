"""A fixed conversation script, for measuring the AI's replies rather than its luck.

`level_compliance_rate` asks a question about the AI's side of a conversation, so
the learner's side has to be held still. Generating a fresh learner turn each time
would make a before-and-after comparison a comparison of two different
conversations.

WRITTEN FRESH, AND CHECKED. No line here matches an item in the held-out split —
`tests/test_script.py` fails if one ever does. Feeding a `test` sentence to the
dialogue model would push it through the conversation prompt, and that split is
touched once this month and not by this.

The first draft said "not one line comes from data/evaluation" and was wrong: two
lines matched `test` items verbatim and six matched `dev` ones. Set phrases are a
small, closed set, so 「おはようございます。」 and 「よろしくお願いします。」 coincide
with the reference answers whatever anyone intends. The `test` collisions were
replaced; the `dev` ones are left, because the script never reaches the correction
engine and `dev` is the side that may be tuned against anyway.

It also would not be a conversation if lifted from there: the evaluation items are
isolated sentences, and what is needed here is five turns that follow on from each
other and from the partner's opening line in dialogue/scenes.py.

DELIBERATELY CORRECT-ISH JAPANESE. These are not learner mistakes to be corrected;
they are prompts to make the partner talk. A script full of errors would measure
how the partner reacts to errors, which is the correction engine's question, not
this one.
"""

from __future__ import annotations

from typing import Final

# Five learner turns per scene, following the partner's opening line. Kept short
# and ordinary, the way a beginner actually writes: the point is to give the model
# somewhere natural to go, not to test it.
SCRIPT: Final[dict[str, tuple[str, ...]]] = {
    "greeting": (
        "おはようございます。",
        "はい、元気です。",
        "今日はいい天気ですね。",
        "これから駅に行きます。",
        "はい、また明日。",
    ),
    "self_introduction": (
        "はじめまして。ラフルです。",
        "インドから来ました。",
        "エンジニアです。",
        "日本語を少し勉強しています。",
        "よろしくお願いします。",
    ),
    "thanks": (
        "ありがとうございます。",
        "はい、重かったです。",
        "とても助かりました。",
        "いいえ、大丈夫です。",
        "本当にありがとうございました。",
    ),
    "simple_request": (
        "すみません。",
        "水をください。",
        "これはいくらですか。",
        "はい、お願いします。",
        "ありがとうございました。",
    ),
    "delay_notice": (
        "すみません、少し遅れます。",
        "電車がまだ動きません。",
        "たぶん十分ぐらいです。",
        "はい、着いたら連絡します。",
        "ご迷惑をおかけします。",
    ),
    "workplace_keigo": (
        "おはようございます。",
        "はい、資料は今日できます。",
        "少し時間がかかります。",
        "はい、確認してから送ります。",
        "では、また明日。",
    ),
}

TURNS: Final = 5
