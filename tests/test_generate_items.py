"""Tests for what the candidate generator is told.

Only the prompt is tested here. What the model writes back is checked by a native
speaker before any of it becomes an item, so asserting on generated Japanese would
duplicate that check badly; what is worth pinning is the input, because a criterion
that quietly stops being sent produces candidates that look exactly as good and are
labelled wrong (evals/generate_items.py, "WHAT CHANGED IN v2").
"""

from __future__ import annotations

from dialogue.scenes import POLITENESS_ADJUDICATIONS, SCENES, politeness_floor
from evals.generate_items import scene_prompt


def prompt_for(scene: str) -> str:
    return scene_prompt(scene, needs_count=9, natural_count=3, avoid=[])


def test_the_generator_is_given_the_worked_cases_not_just_the_floor() -> None:
    """The half of the politeness rule that settles the borderline calls.

    The rule was split on 2026-08-09 so the rater's form could stop printing
    evaluation items, and the two halves are now a `politeness_floor` /
    `politeness_rule` pair that differ by one word at the call site. Labelling wants
    the whole thing: v1 of this prompt omitted the criteria and 12 of its 14
    overturned candidates came from exactly that.
    """
    for scene, adjudication in POLITENESS_ADJUDICATIONS.items():
        assert adjudication in prompt_for(scene)


def test_every_scene_states_its_floor_and_tier() -> None:
    for scene in SCENES:
        tier, floor = politeness_floor(scene)
        prompt = prompt_for(scene)
        assert floor in prompt
        assert f"tier {tier}" in prompt


def test_the_counts_asked_for_are_the_counts_given() -> None:
    """A miscount here lands in the dataset as a skewed true/false balance.

    Each count is asserted with the label it belongs to. Matching "7 sentences" on
    its own passes just as happily when the two are swapped, which is the mistake
    worth catching — the totals stay right and the 90:30 balance quietly inverts.
    """
    prompt = scene_prompt("greeting", needs_count=7, natural_count=2, avoid=[])

    assert '7 sentences labelled "needs_correction"' in prompt
    assert '2 sentences labelled "natural"' in prompt


def test_existing_sentences_are_passed_on_to_be_avoided() -> None:
    prompt = scene_prompt("greeting", 9, 3, avoid=["おはようです。", "元気？"])

    assert "おはようです。" in prompt
    assert "元気？" in prompt


def test_a_focus_reaches_the_prompt_only_when_asked_for() -> None:
    """`--focus` aims a replacement batch at the mistake types the dataset lacks."""
    assert "counters" in scene_prompt("greeting", 9, 3, avoid=[], focus="counters")
    assert "This batch is replacing" not in prompt_for("greeting")
