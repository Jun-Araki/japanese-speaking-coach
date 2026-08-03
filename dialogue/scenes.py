"""Scenes and levels, exactly as fixed in docs/ja/glossary.md sections 3 and 4.

These identifiers label every evaluation item and every run record, so they are
not free text. Changing one invalidates data already labelled with it.

The learner-facing labels are English: the testers are learners in Bangalore, and
the app's own interface is not the thing being practised.
"""

from __future__ import annotations

from typing import Final

# Ordered easiest first. Beginners are not expected to reach the later ones.
SCENES: Final[dict[str, str]] = {
    "greeting": "Greeting",
    "self_introduction": "Introducing yourself",
    "thanks": "Saying thank you",
    "simple_request": "Asking for something",
    "delay_notice": "Saying you will be late",
    "workplace_keigo": "Workplace keigo",
}

# What the partner is, and what they open with. The partner always speaks first so
# the learner has something to answer -- a beginner staring at an empty box writes
# nothing, and a session with no learner sentence produces nothing to correct.
SCENE_BRIEFS: Final[dict[str, tuple[str, str]]] = {
    "greeting": (
        "You are a neighbour the learner passes in the morning. Keep it short and warm.",
        "おはようございます。",
    ),
    "self_introduction": (
        "You are meeting the learner for the first time at a small gathering. "
        "Ask about their name, work or where they are from, one thing at a time.",
        "はじめまして。お名前は何ですか。",
    ),
    "thanks": (
        "You are a colleague who has just helped the learner carry something heavy.",
        "どういたしまして。大丈夫でしたか。",
    ),
    "simple_request": (
        "You work at a small shop and the learner is a customer who needs something.",
        "いらっしゃいませ。何かお探しですか。",
    ),
    "delay_notice": (
        "You are a colleague waiting for the learner, who is running late. "
        "You are not annoyed.",
        "もしもし。今どちらですか。",
    ),
    "workplace_keigo": (
        "You are the learner's manager at a Japanese company. You speak politely "
        "and expect polite speech in return, but you are not harsh.",
        "お疲れさまです。少しいいですか。",
    ),
}

LEVELS: Final[dict[str, str]] = {
    "beginner": "Beginner",
    "upper_beginner": "Upper beginner",
    "intermediate": "Intermediate",
}

# "Roughly" is deliberate: no JLPT past papers or textbooks are ingested, so the
# mapping is an approximation and is described as one in the README too.
LEVEL_BRIEFS: Final[dict[str, str]] = {
    "beginner": (
        "Roughly JLPT N5. Use only the most common words and the plainest です/ます "
        "sentences. Avoid subordinate clauses entirely."
    ),
    "upper_beginner": (
        "Roughly JLPT N4. Common everyday words, simple て-form and past tense. "
        "At most one clause of subordination."
    ),
    "intermediate": (
        "Roughly JLPT N3. Everyday vocabulary including some abstract words, and "
        "normal connected sentences."
    ),
}


def scene_brief(scene: str) -> tuple[str, str]:
    """Return the partner's role and opening line for a scene."""
    if scene not in SCENE_BRIEFS:
        raise ValueError(f"Unknown scene: {scene!r}")
    return SCENE_BRIEFS[scene]


def level_brief(level: str) -> str:
    """Return the language ceiling for a level."""
    if level not in LEVEL_BRIEFS:
        raise ValueError(f"Unknown level: {level!r}")
    return LEVEL_BRIEFS[level]
