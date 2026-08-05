"""The evaluation dataset: what one item is, and how the splits are assigned.

The dataset is the main public artefact of this project, so the shape here is the
shape in docs/ja/functional-design.md, key for key. It is read by the scoring
script and by nothing else — no part of the app touches it.

Labelling authority sits with the native speaker, not with this module and not
with the model that produced the candidates. See generate_items.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from dialogue.scenes import SCENES

Split = Literal["dev", "test"]

ITEMS_PATH: Final = Path("data/evaluation/items.json")

# Every third item goes to test. The counter runs across the whole batch rather
# than restarting per scene, because restarting leaves the small false-labelled
# groups entirely in dev: a scene with two `false` items would send neither of
# them to test, and over_correction_rate is measured on test.
TEST_EVERY: Final = 3


@dataclass(frozen=True)
class Item:
    """One evaluation item.

    `corrected_sentence` and `reason_en` are None exactly when `needs_correction`
    is False. A sentence that was already fine has nothing to show, and carrying a
    "you could also say" on those items would quietly teach the scorer that an
    unnecessary correction was expected.
    """

    id: str
    scene: str
    learner_sentence: str
    needs_correction: bool
    corrected_sentence: str | None
    reason_en: str | None
    split: Split

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "scene": self.scene,
            "learner_sentence": self.learner_sentence,
            "needs_correction": self.needs_correction,
        }
        if self.needs_correction:
            payload["corrected_sentence"] = self.corrected_sentence
            payload["reason_en"] = self.reason_en
        payload["split"] = self.split
        return payload


def load_items(path: Path = ITEMS_PATH) -> list[Item]:
    """Read the dataset. Raises rather than skipping a malformed item."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path} does not contain a list of items")
    return [_item_from_json(entry, index) for index, entry in enumerate(raw)]


def save_items(items: list[Item], path: Path = ITEMS_PATH) -> None:
    """Write the dataset, one item per line group, with Japanese left readable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [item.to_json() for item in items]
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def assign_splits(items: list[Item], start_index: int = 0) -> list[Item]:
    """Return the items with `split` filled in, two dev for every one test.

    Called once per batch and never again. The 60 items labelled on day 3 keep the
    split they were given here when day 6 adds the next 60: re-assigning the whole
    dataset would move test items into dev after a baseline had already been
    measured on them, which breaks "test is touched at the start and at the end"
    without anything failing visibly (docs/ja/glossary.md §7).

    Ordering is by scene, then `true` before `false`, then id. It is deterministic
    on purpose — the same input has to produce the same splits on a re-run, or the
    dataset stops being reproducible from the candidates it came from.
    """
    scene_order = list(SCENES)
    ordered = sorted(
        items,
        key=lambda item: (scene_order.index(item.scene), not item.needs_correction, item.id),
    )
    by_id = {
        item.id: _replace_split(
            item, "test" if (start_index + position) % TEST_EVERY == TEST_EVERY - 1 else "dev"
        )
        for position, item in enumerate(ordered)
    }
    # Back into the caller's order, so a diff of items.json stays readable.
    return [by_id[item.id] for item in items]


def counts_by_scene(items: list[Item]) -> dict[str, dict[str, int]]:
    """Per scene: how many items, how many need correction, how many are test.

    Used by the day 6 machine check and when deciding what the next batch has to
    contain. Counting 120 items by eye is how a dataset ends up 89:31.
    """
    summary: dict[str, dict[str, int]] = {
        scene: {"total": 0, "needs_correction": 0, "natural": 0, "dev": 0, "test": 0}
        for scene in SCENES
    }
    for item in items:
        row = summary[item.scene]
        row["total"] += 1
        row["needs_correction" if item.needs_correction else "natural"] += 1
        row[item.split] += 1
    return summary


def _replace_split(item: Item, split: Split) -> Item:
    return Item(
        id=item.id,
        scene=item.scene,
        learner_sentence=item.learner_sentence,
        needs_correction=item.needs_correction,
        corrected_sentence=item.corrected_sentence,
        reason_en=item.reason_en,
        split=split,
    )


def _item_from_json(entry: Any, index: int) -> Item:
    if not isinstance(entry, dict):
        raise ValueError(f"item {index} is not an object")

    def required(key: str) -> Any:
        if key not in entry:
            raise ValueError(f"item {index} has no {key!r}")
        return entry[key]

    needs_correction = required("needs_correction")
    if not isinstance(needs_correction, bool):
        raise ValueError(f"item {index}: needs_correction is not a boolean")

    scene = required("scene")
    if scene not in SCENES:
        raise ValueError(f"item {index}: unknown scene {scene!r}")

    split = required("split")
    if split not in ("dev", "test"):
        raise ValueError(f"item {index}: unknown split {split!r}")

    return Item(
        id=str(required("id")),
        scene=str(scene),
        learner_sentence=str(required("learner_sentence")),
        needs_correction=needs_correction,
        corrected_sentence=entry.get("corrected_sentence") if needs_correction else None,
        reason_en=entry.get("reason_en") if needs_correction else None,
        split=split,
    )
