"""The annotations `retrieval_hit_rate` is scored against.

The worksheet is the one artefact in this repository that cannot be rebuilt. The
sample can be redrawn by rerunning the script; the grounds are judgements made
while no retrieval existed, and once search results have been seen nobody can make
them again. So the checks here are about the file staying whole and staying
readable, not about the script's arithmetic.

Every failure mode below ends in the same place: a number that looks like a
measurement of the index and is really a measurement of a typo.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from evals.dataset import ITEMS_PATH, load_items
from evals.retrieval_kit import (
    KIT_DIR,
    THRESHOLD_SAMPLE,
    WORKSHEET_PATH,
    WorksheetError,
    accepted_overlap,
    article_texts,
    articles,
    is_filled,
    lexical_share,
    lexical_source,
    load_grounds,
    reference_text,
    select,
)


def _sample() -> list[str]:
    return [item.id for item in select(load_items(ITEMS_PATH))]


def _printed_shares() -> dict[str, tuple[str, str]]:
    """Each item's written share and the article it was found in."""
    found: dict[str, tuple[str, str]] = {}
    current = ""
    for raw in WORKSHEET_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("### ") and len(line.split()) > 2:
            current = line.split()[2]
        elif line.startswith("- lexical_share:"):
            written = line.removeprefix("- lexical_share:").strip()
            share, _, source = written.partition(" ")
            found[current] = (share, source.strip("()"))
    return found


class TestTheFilledWorksheet:
    def test_every_sampled_item_has_an_answer(self) -> None:
        # Not "most". A blank read as `none` becomes a finding about the reference.
        assert sorted(load_grounds()) == sorted(_sample())

    def test_every_article_named_exists(self) -> None:
        known = set(articles())

        named = {one for ids in load_grounds().values() for one in ids}

        assert named <= known

    def test_the_sample_is_the_one_the_answers_were_written_against(self) -> None:
        # Redrawing the sample after annotating would silently pair answers with
        # different sentences. The order matters too: the first ten set the
        # threshold and the rest are published, and swapping them moves an item
        # from unpublished to published without anyone deciding to.
        assert list(load_grounds()) == _sample()

    def test_no_sampled_item_is_held_out(self) -> None:
        held_out = {item.id for item in load_items(ITEMS_PATH) if item.split == "test"}

        assert set(load_grounds()) & held_out == set()

    def test_no_sampled_item_is_quoted_whole_in_the_reference(self) -> None:
        assert set(load_grounds()) & accepted_overlap() == set()

    def test_the_printed_overlap_still_matches_the_reference(self) -> None:
        # The shares were written down before the grounds were, and each item's
        # result is published beside its share. Editing an article moves them, and a
        # disclosure against stale numbers discloses nothing. This test going red
        # means the shares have to be recomputed — not that the grounds have to be
        # touched.
        items = {item.id: item for item in load_items(ITEMS_PATH)}
        corpus = reference_text()
        printed = _printed_shares()

        # The count is asserted first. An earlier version iterated the parsed shares
        # and checked each against the reference, which passes perfectly when every
        # share line has been deleted — the 8/13 audit removed all thirty and no
        # test went red.
        assert len(printed) == len(_sample())

        # Compared as the two decimals that were written, not as floats: the file
        # holds a rounded string, and 0.38 against 0.375 is a tolerance argument
        # rather than a disagreement.
        for item_id, (share, source) in printed.items():
            sentence = items[item_id].learner_sentence
            assert share == f"{lexical_share(sentence, corpus):.2f}", item_id
            assert source == lexical_source(sentence), item_id

    def test_each_item_sits_under_the_block_it_is_scored_in(self) -> None:
        # The published/unpublished split is positional — `load_grounds` order,
        # sliced at THRESHOLD_SAMPLE — and nothing tied a position to the heading
        # printed above it. The audit swapped the two `##` headings and the whole
        # suite stayed green, which moves ten items from unpublished to published
        # with one edit.
        blocks: list[tuple[str, str]] = []
        heading = ""
        for raw in WORKSHEET_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("## ") and "sample" in line.lower():
                heading = line
            elif line.startswith("### ") and len(line.split()) > 2:
                blocks.append((line.split()[2], heading))

        under = {item_id: heading for item_id, heading in blocks}
        answered = list(load_grounds())
        for item_id in answered[:THRESHOLD_SAMPLE]:
            assert "Threshold-setting" in under[item_id], item_id
        for item_id in answered[THRESHOLD_SAMPLE:]:
            assert "Measurement" in under[item_id], item_id

    def test_the_recorded_selection_still_matches_the_sheet(self) -> None:
        # selection.json is the artefact a reader cites as the pre-registered
        # sample, and nothing read it back — it could be hand-edited, or go stale
        # when items.json changed, with the suite green either way.
        recorded = json.loads((KIT_DIR / "selection.json").read_text(encoding="utf-8"))
        answered = list(load_grounds())

        assert recorded["threshold_sample"] == answered[:THRESHOLD_SAMPLE]
        assert recorded["measurement_sample"] == answered[THRESHOLD_SAMPLE:]
        assert recorded["articles"] == articles()
        assert recorded["excluded_for_verbatim_overlap"] == sorted(accepted_overlap())

    def test_the_two_blocks_are_the_sizes_the_design_fixed(self) -> None:
        answered = list(load_grounds())

        assert len(answered[:THRESHOLD_SAMPLE]) == 10
        assert len(answered[THRESHOLD_SAMPLE:]) == 20


class TestTheSecondAnnotation:
    """The control kept beside the sheet, so its agreement figure stays checkable."""

    PATH = KIT_DIR / "second-annotation.md"

    def _parsed(self) -> dict[str, frozenset[str]]:
        found: dict[str, frozenset[str]] = {}
        for line in self.PATH.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^(eval-\d+):\s*([^|]+)\|", line)
            if match:
                written = match.group(2).strip()
                found[match.group(1)] = (
                    frozenset()
                    if written == "none"
                    else frozenset(one.strip() for one in written.split(","))
                )
        return found

    def test_it_is_still_thirty_readable_answers(self) -> None:
        assert len(self._parsed()) == 30

    def test_it_names_no_article_that_does_not_exist(self) -> None:
        named = {one for ids in self._parsed().values() for one in ids}

        assert named <= set(articles())

    def test_it_annotates_items_that_exist(self) -> None:
        known = {item.id for item in load_items(ITEMS_PATH)}

        assert set(self._parsed()) <= known


class TestReadingTheForm:
    def _write(self, tmp_path: Path, grounds: str) -> Path:
        path = tmp_path / "worksheet.md"
        path.write_text(
            f"### 1. eval-001 · greeting · needs correction\n\n- grounds: {grounds}\n",
            encoding="utf-8",
        )
        return path

    def test_a_blank_answer_is_refused_rather_than_read_as_none(self, tmp_path: Path) -> None:
        with pytest.raises(WorksheetError, match="no grounds"):
            load_grounds(self._write(tmp_path, ""))

    def test_an_article_that_does_not_exist_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(WorksheetError, match="no such article"):
            load_grounds(self._write(tmp_path, "grammar-009"))

    def test_none_is_an_answer(self, tmp_path: Path) -> None:
        assert load_grounds(self._write(tmp_path, "none")) == {"eval-001": ()}

    def test_more_than_one_article_is_an_answer(self, tmp_path: Path) -> None:
        loaded = load_grounds(self._write(tmp_path, "grammar-001, grammar-003"))

        assert loaded == {"eval-001": ("grammar-001", "grammar-003")}

    def test_an_indented_answer_is_still_read(self, tmp_path: Path) -> None:
        # What a markdown formatter does to a list under a heading. Before 8/13 this
        # was not read, which by itself would only have lost an answer — but it also
        # made `is_filled` report an untouched sheet, and the next run of the script
        # regenerated over thirty annotations that exist nowhere else.
        path = tmp_path / "worksheet.md"
        path.write_text(
            "  ### 1. eval-001 · greeting\n\n  - grounds: grammar-001\n", encoding="utf-8"
        )

        assert load_grounds(path) == {"eval-001": ("grammar-001",)}
        assert is_filled(path)

    def test_an_item_with_no_grounds_line_is_refused(self, tmp_path: Path) -> None:
        # Silently absent from the dict before 8/13. Only the whole-key-set test
        # upstream noticed, and only for this one sheet.
        path = tmp_path / "worksheet.md"
        path.write_text(
            "### 1. eval-001 · greeting\n\n### 2. eval-002 · greeting\n\n- grounds: none\n",
            encoding="utf-8",
        )

        with pytest.raises(WorksheetError, match="eval-001 has no grounds"):
            load_grounds(path)

    def test_a_trailing_item_with_no_grounds_line_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "worksheet.md"
        path.write_text("### 1. eval-001 · greeting\n\n- learner: あ\n", encoding="utf-8")

        with pytest.raises(WorksheetError, match="eval-001 has no grounds"):
            load_grounds(path)

    def test_an_answer_with_no_item_above_it_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "worksheet.md"
        path.write_text("- grounds: grammar-001\n", encoding="utf-8")

        with pytest.raises(WorksheetError, match="no item above it"):
            load_grounds(path)

    def test_the_same_item_answered_twice_is_refused(self, tmp_path: Path) -> None:
        # Last-wins is the worst of the three options: the sheet shows two answers
        # and the number uses one, with nothing saying which.
        path = tmp_path / "worksheet.md"
        path.write_text(
            "### 1. eval-001 · greeting\n\n- grounds: none\n\n"
            "### 2. eval-001 · greeting\n\n- grounds: grammar-001\n",
            encoding="utf-8",
        )

        with pytest.raises(WorksheetError, match="appears twice"):
            load_grounds(path)

    def test_a_heading_that_is_not_an_item_is_ignored(self, tmp_path: Path) -> None:
        # A reviewer writing "### Review notes" on the sheet used to get an
        # IndexError, which no caller catching WorksheetError would handle.
        path = tmp_path / "worksheet.md"
        path.write_text(
            "### Review notes\n\n### 1. eval-001 · greeting\n\n- grounds: none\n",
            encoding="utf-8",
        )

        assert load_grounds(path) == {"eval-001": ()}


class TestTheRerunGuard:
    def test_a_filled_sheet_is_recognised(self) -> None:
        assert is_filled(WORKSHEET_PATH)

    def test_a_blank_sheet_is_not(self, tmp_path: Path) -> None:
        path = tmp_path / "worksheet.md"
        path.write_text("### 1. eval-001 · greeting\n\n- grounds: \n", encoding="utf-8")

        assert not is_filled(path)

    def test_a_missing_sheet_is_not(self, tmp_path: Path) -> None:
        assert not is_filled(tmp_path / "nothing.md")


class TestLexicalShare:
    def test_a_phrase_lifted_from_the_reference_scores_one(self) -> None:
        assert lexical_share("どこに住んでいますか。", reference_text()) == 1.0

    def test_a_sentence_the_reference_never_says_scores_low(self) -> None:
        # Nothing to do with beginner Japanese, so only stray single characters match.
        assert lexical_share("量子力学の講義は木曜日でした。", reference_text()) < 0.4

    def test_an_empty_sentence_does_not_divide_by_zero(self) -> None:
        assert lexical_share("。", reference_text()) == 0.0

    def test_a_match_cannot_be_assembled_from_two_articles(self) -> None:
        # The corpus is one string, so without a separator a "verbatim" run could
        # start in grammar-001 and finish in grammar-002 — text that exists in no
        # document and could never be retrieved.
        texts = list(article_texts().values())
        across = texts[0][-4:] + texts[1][:4]

        assert across in "".join(texts)
        assert across not in reference_text()

    def test_the_source_names_the_article_the_run_was_found_in(self) -> None:
        # Signs the share. Without it a high overlap with the WRONG article reads as
        # "this item was easy", when it means the opposite.
        assert lexical_source("どこに住んでいますか。") == "grammar-001"
        assert lexical_source("量子力学の講義は木曜日でした。") != ""
