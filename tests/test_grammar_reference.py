"""The grammar reference must not quote the evaluation set back at itself.

Retrieval hands the model the reference articles. An article that contains an
item's learner sentence, its reference answer or its reason is handing over the
answer to that item, and `retrieval_hit_rate` then measures string matching while
being reported as grammar. Week 1 found this by hand and fixed the examples; this
is the machinery that keeps it fixed.

Two different rules for the two splits, because the risk is different.

`test` is a hard failure. Those items are measured once more in week 4, against a
corpus that will by then have been retrieved from; an answer sitting in it is the
kind of contamination that cannot be undone afterwards.

`dev` is an allow-list of ids, not a count. Set phrases cannot be explained without
writing them down — おはようございます, はじめまして, お願いします — so the overlap
cannot go to zero. A count would let a new collision be waved through by editing
one digit, and the diff would show a number changing. An id has to be added by
name, on a line where a reason can be written.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from evals.dataset import ITEMS_PATH, Item, load_items

GRAMMAR_DIR = Path("data/grammar")

# Punctuation is dropped before comparing. A rule that mentions a phrase writes it
# without the closing 。, which is how 「はじめまして」 slipped past an equality check
# in week 1 while sitting in the article as the answer to eval-017.
_PUNCTUATION = re.compile(r"[。、？！「」\s]")


def normalise(text: str) -> str:
    return _PUNCTUATION.sub("", text)


# Every `dev` item whose text appears verbatim in the reference, checked and left
# there. All of them are set phrases: the article cannot teach 「お願いします」
# without writing 「お願いします」. Adding to this list is a decision, so it is made
# here rather than by moving a number.
ACCEPTED_OVERLAP_PATH = GRAMMAR_DIR / "accepted_overlap.json"


def accepted_overlap() -> frozenset[str]:
    """Dev ids whose text is in the reference on purpose, with a reason each.

    Data rather than a literal in this file, because `evals/retrieval_kit.py` needs
    the same list to keep them out of the sample it draws — and production code
    reading a constant out of a test file is the wrong direction of dependency.
    """
    loaded = json.loads(ACCEPTED_OVERLAP_PATH.read_text(encoding="utf-8"))
    return frozenset(loaded["items"])


# Eleven of the twelve are labelled as needing correction, so what they inflate is
# `detection_accuracy` rather than `over_correction_rate`. The two items the audit
# found stating a `false` item's answer outright — eval-009 in grammar-008 and
# eval-034 in grammar-003 — were removed by rewriting the examples and keeping the
# rules, which is the distinction that matters: a general rule is grounding, the
# sentence out of the answer key is the answer.


def reference_text() -> str:
    articles = (path.read_text(encoding="utf-8") for path in sorted(GRAMMAR_DIR.glob("*.md")))
    return normalise("\n".join(articles))


def quoted_items(items: list[Item], corpus: str) -> set[str]:
    found = set()
    for item in items:
        for text in (item.learner_sentence, item.corrected_sentence, item.reason_en):
            if text and normalise(text) in corpus:
                found.add(item.id)
    return found


class TestGrammarReference:
    def test_no_held_out_item_appears_in_the_reference(self) -> None:
        items = [item for item in load_items(ITEMS_PATH) if item.split == "test"]

        assert quoted_items(items, reference_text()) == set()

    def test_the_dev_overlap_is_the_one_that_was_accepted(self) -> None:
        items = [item for item in load_items(ITEMS_PATH) if item.split == "dev"]

        assert quoted_items(items, reference_text()) == accepted_overlap()

    def test_the_allow_list_cannot_absorb_a_held_out_item(self) -> None:
        # The list exists to accept collisions that cannot be avoided. It must not
        # become the place a `test` collision goes to be forgotten.
        held_out = {item.id for item in load_items(ITEMS_PATH) if item.split == "test"}

        assert accepted_overlap() & held_out == set()
