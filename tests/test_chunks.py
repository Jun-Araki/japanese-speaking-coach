"""Tests for splitting the grammar reference into indexable sections.

Two things are pinned here, and the second is the one that matters.

The first is the split itself: sections stay whole, the introductory paragraph is
not thrown away, and no chunk contains text this module composed rather than read.

The second is that the CITATION CHECK APPLIES TO WHAT IS ACTUALLY INDEXED.
`tests/test_grammar_reference.py` checks the articles as files. Retrieval does not
hand the model a file, it hands it a chunk — so the same rule is applied again over
the chunks, before any of them reach Chroma. Today the two are the same text and
the check is redundant; the day a chunk is built by joining, summarising or
templating anything, it stops being redundant and starts being the only check that
would notice.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.dataset import ITEMS_PATH, load_items
from evals.retrieval_kit import normalise
from retrieval.chunks import GRAMMAR_DIR, Chunk, article_metadata, load_chunks, split_article

ARTICLE = """\
---
id: grammar-999
title: "A test article"
also_see: [grammar-001]
---

# A test article

The paragraph before any heading, which says what is being contrasted.

## First section

Body of the first section.

## Second section

Body of the second section.
"""


def chunks() -> list[Chunk]:
    return load_chunks()


class TestSplitting:
    def test_each_section_becomes_its_own_chunk(self) -> None:
        result = split_article(ARTICLE, "grammar-999", "A test article")

        assert [chunk.heading for chunk in result] == [
            "A test article",
            "First section",
            "Second section",
        ]
        assert [chunk.id for chunk in result] == [
            "grammar-999#0",
            "grammar-999#1",
            "grammar-999#2",
        ]

    def test_the_paragraph_before_the_first_heading_is_kept(self) -> None:
        # It is the only place an article says why the distinction exists. Dropping
        # it, or gluing it onto the first section, loses the one chunk that answers
        # "why are there two particles here at all".
        preamble = split_article(ARTICLE, "grammar-999", "A test article")[0]

        assert preamble.body.startswith("The paragraph before any heading")
        # The level-one title is already carried as article_title; leaving it in the
        # body would put it into the vector twice.
        assert "# A test article" not in preamble.body

    def test_a_section_body_stops_at_the_next_heading(self) -> None:
        first = split_article(ARTICLE, "grammar-999", "A test article")[1]

        assert first.body == "Body of the first section."

    def test_embedding_text_carries_the_context_the_body_lacks(self) -> None:
        # A section called "Negatives" is meaningless on its own, and a body about
        # 「住む」 never repeats that the article is about places.
        section = split_article(ARTICLE, "grammar-999", "A test article")[1]

        assert section.embedding_text.startswith("A test article\nFirst section\n")
        assert section.body in section.embedding_text


class TestFrontmatter:
    def test_reads_the_id_and_title(self) -> None:
        assert article_metadata(ARTICLE, Path("x.md")) == ("grammar-999", "A test article")

    def test_refuses_an_article_with_no_frontmatter(self) -> None:
        # Falling back to the filename would index the article under an id that
        # names no article, and a grounding id that cannot be looked up is worse
        # than showing the learner no citation at all.
        with pytest.raises(ValueError, match="frontmatter"):
            article_metadata("# Just a heading\n", Path("x.md"))

    def test_refuses_an_article_missing_the_id(self) -> None:
        with pytest.raises(ValueError, match="missing id or title"):
            article_metadata('---\ntitle: "No id"\n---\n\n# Body\n', Path("x.md"))


class TestTheRealCorpus:
    def test_every_article_is_split_into_more_than_one_chunk(self) -> None:
        # The point of the exercise. An article embedded whole is an average of the
        # four or five contrasts it covers.
        by_article: dict[str, int] = {}
        for chunk in chunks():
            by_article[chunk.article_id] = by_article.get(chunk.article_id, 0) + 1

        assert len(by_article) == len(list(GRAMMAR_DIR.glob("*.md")))
        assert all(count > 1 for count in by_article.values()), by_article

    def test_no_chunk_can_overflow_the_embedding_model(self) -> None:
        # Measured 2026-08-19 against intfloat/multilingual-e5-small, whose limit is
        # 512 tokens: the largest chunk (grammar-008#1, 1331 characters) tokenised
        # to 473, and the corpus averaged about 2.8 characters per token. The guard
        # is in characters because loading the tokeniser here would mean a test that
        # downloads a model, which this repository does not do — so the budget keeps
        # headroom instead. Truncation is silent and would surface only as a hit
        # rate that is worse than it should be, with no visible cause.
        budget = 1400
        for chunk in chunks():
            assert len(chunk.body) <= budget, f"{chunk.id} is {len(chunk.body)} characters"

    def test_chunk_ids_are_unique(self) -> None:
        ids = [chunk.id for chunk in chunks()]

        assert len(ids) == len(set(ids))

    def test_every_chunk_body_appears_verbatim_in_its_article(self) -> None:
        # No chunk may contain text that this module wrote. If one does, the
        # citation checks below are comparing against something that is not in the
        # repository, and the corpus stops being auditable.
        sources = {}
        for path in GRAMMAR_DIR.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            # Keyed by the id in the frontmatter, not by the filename: the two agree
            # today, and the id is the one retrieval will cite.
            sources[article_metadata(text, path)[0]] = text
        for chunk in chunks():
            assert chunk.body in sources[chunk.article_id], chunk.id

    def test_no_line_of_an_article_is_lost(self) -> None:
        # Splitting must not silently drop content: a rule that lands between two
        # chunks is a rule retrieval can never return.
        for path in sorted(GRAMMAR_DIR.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            article_id, _ = article_metadata(text, path)
            body = "\n".join(chunk.body for chunk in chunks() if chunk.article_id == article_id)
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith(("#", "---", "id:", "title:", "also_see:")):
                    continue
                assert stripped in body, f"{path.name}: {stripped!r}"


class TestChunksDoNotQuoteTheEvaluationSet:
    """The same rule as tests/test_grammar_reference.py, over what is indexed."""

    def indexed_text(self) -> str:
        return normalise("\n".join(chunk.embedding_text for chunk in chunks()))

    def test_no_held_out_item_appears_in_any_chunk(self) -> None:
        corpus = self.indexed_text()
        held_out = [item for item in load_items(ITEMS_PATH) if item.split == "test"]

        quoted = {
            item.id
            for item in held_out
            for text in (item.learner_sentence, item.corrected_sentence, item.reason_en)
            if text and normalise(text) in corpus
        }
        assert quoted == set()

    def test_the_dev_overlap_is_still_the_accepted_one(self) -> None:
        corpus = self.indexed_text()
        dev = [item for item in load_items(ITEMS_PATH) if item.split == "dev"]
        accepted = json.loads(
            (GRAMMAR_DIR / "accepted_overlap.json").read_text(encoding="utf-8")
        )["items"]

        quoted = {
            item.id
            for item in dev
            for text in (item.learner_sentence, item.corrected_sentence, item.reason_en)
            if text and normalise(text) in corpus
        }
        assert quoted == set(accepted)
