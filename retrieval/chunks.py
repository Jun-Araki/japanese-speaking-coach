"""Splitting the grammar reference into the pieces that get embedded.

ONE ARTICLE IS NOT ONE CHUNK. The articles run to about sixty lines and cover four
or five contrasts each — grammar-001 alone holds で against に, に for clock times,
を for leaving a place, and へ against から. Embedded whole, an article becomes an
average of everything it says, and a learner sentence about clock times competes
against the same blurred vector as one about leaving a station. Split by section,
the vector for "に also marks a point on the clock" is about clock times and
nothing else.

WHAT GOES INTO THE VECTOR IS NOT WHAT IS SHOWN. A section body says 「住む」 takes
に without repeating that the article is about places at all, and the shortest
headings — "Negatives", "Leaving the particle out" — are meaningless alone. So the
title and heading are prepended for embedding, while `body` stays exactly as
written so that the citation check compares against the file rather than against
something this module composed.

The section heading is the split point rather than a character count. A fixed
window would cut through the middle of a contrast, leaving the wrong half to be
retrieved: an article that says ✗ X → ✓ Y is useless from the ✗ side alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

GRAMMAR_DIR: Final = Path("data/grammar")

# The frontmatter block, and the fields read out of it. Parsed with a regex rather
# than a YAML dependency: three fixed keys, written by hand, in eight files.
_FRONTMATTER: Final = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_ID: Final = re.compile(r"^id:\s*(\S+)\s*$", re.MULTILINE)
_TITLE: Final = re.compile(r'^title:\s*"?(.*?)"?\s*$', re.MULTILINE)

# A level-two heading at the start of a line. Level one is the article title, which
# is not a section: it introduces the whole file and would otherwise become a chunk
# holding every section under it.
_SECTION: Final = re.compile(r"^## +(.*)$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    """One section of one article, and where it came from.

    `id` carries the article id in front of the section number, so a grounding id
    shown to a learner can be reduced to the article it came from without a lookup
    — and so a retrieval result that names a section can still be read as "this
    article, this part of it".
    """

    id: str
    article_id: str
    article_title: str
    heading: str
    body: str

    @property
    def embedding_text(self) -> str:
        """Title, heading and body, in the order a reader would meet them."""
        return f"{self.article_title}\n{self.heading}\n{self.body}".strip()


def split_article(text: str, article_id: str, article_title: str) -> list[Chunk]:
    """Split one article's text at its section headings.

    The text before the first heading — the paragraph that says what the whole
    article is contrasting — becomes a chunk of its own rather than being dropped
    or glued onto the first section. It is the only place the articles explain why
    the distinction exists, which is what a learner asking about it needs.
    """
    body = _FRONTMATTER.sub("", text)
    matches = list(_SECTION.finditer(body))

    chunks: list[Chunk] = []
    preamble = (body[: matches[0].start()] if matches else body).strip()
    if preamble:
        # The level-one title line is dropped: it is already carried as
        # `article_title`, and leaving it in would put it in the vector twice.
        lines = [line for line in preamble.splitlines() if not line.startswith("# ")]
        preamble = "\n".join(lines).strip()
    if preamble:
        chunks.append(
            Chunk(
                id=f"{article_id}#0",
                article_id=article_id,
                article_title=article_title,
                heading=article_title,
                body=preamble,
            )
        )

    for number, match in enumerate(matches, start=1):
        end = matches[number].start() if number < len(matches) else len(body)
        chunks.append(
            Chunk(
                id=f"{article_id}#{number}",
                article_id=article_id,
                article_title=article_title,
                heading=match.group(1).strip(),
                body=body[match.end() : end].strip(),
            )
        )
    return chunks


def article_metadata(text: str, path: Path) -> tuple[str, str]:
    """The id and title from the frontmatter.

    Raises rather than falling back to the filename. An article whose frontmatter
    did not parse would otherwise be indexed under a made-up id, and a grounding id
    that does not name a real article is worse than no citation at all.
    """
    block = _FRONTMATTER.match(text)
    if block is None:
        raise ValueError(f"{path} has no frontmatter block")
    found_id = _ID.search(block.group(1))
    found_title = _TITLE.search(block.group(1))
    if found_id is None or found_title is None:
        raise ValueError(f"{path} is missing id or title in its frontmatter")
    return found_id.group(1), found_title.group(1)


def load_chunks(directory: Path = GRAMMAR_DIR) -> list[Chunk]:
    """Every section of every article, in file order then document order.

    Sorted rather than whatever the filesystem returns: the index is rebuilt at
    startup, and a corpus that arrives in a different order each time produces a
    different tie-break between two equally close sections.
    """
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        article_id, article_title = article_metadata(text, path)
        chunks.extend(split_article(text, article_id, article_title))
    return chunks
