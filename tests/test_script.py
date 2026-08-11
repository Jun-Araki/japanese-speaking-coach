"""The fixed conversation script must not overlap the held-out split.

`evals/script.py` drives the level-compliance measurement, which means every line
goes through the dialogue prompt. A `test` sentence sent through it is a touch of
the held-out split that no run record would show, and the split is touched twice
this month by design and not otherwise.

Written as a test rather than a promise in a docstring because the first draft made
that promise and broke it: two lines matched `test` items word for word. Set
phrases are a closed set — the collision was not carelessness, it was inevitable,
and inevitability is what machinery is for.
"""

from __future__ import annotations

from dialogue.scenes import SCENES
from evals.dataset import ITEMS_PATH, load_items
from evals.script import SCRIPT, TURNS


def script_lines() -> set[str]:
    return {line for turns in SCRIPT.values() for line in turns}


class TestScript:
    def test_no_line_matches_a_held_out_item(self) -> None:
        held_out = {
            text
            for item in load_items(ITEMS_PATH)
            if item.split == "test"
            for text in (item.learner_sentence, item.corrected_sentence)
            if text
        }

        assert script_lines() & held_out == set()

    def test_covers_every_scene_for_the_declared_number_of_turns(self) -> None:
        # The measurement multiplies these out into its `n`, so a short scene would
        # quietly shrink the denominator rather than fail.
        assert set(SCRIPT) == set(SCENES)
        assert all(len(turns) >= TURNS for turns in SCRIPT.values())
