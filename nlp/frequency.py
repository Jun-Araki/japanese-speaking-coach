"""Difficulty tiers for Japanese words, derived from a published frequency list.

WHY THIS FILE EXISTS AT ALL. `config/thresholds.toml` said the tiers came from
SudachiDict. They do not: SudachiPy exposes surface, lemma, reading and part of
speech, and nothing about how common a word is. `get_word_info()` is deprecated
and carries no frequency either, and the shipped dictionary is compiled — the CSV
that holds the cost column is not in the package. The tokenizer was never the
problem; the tier source was missing, and week 2 found that out by looking.

SOURCE. The word frequency lists of the Balanced Corpus of Contemporary Written
Japanese (BCCWJ), National Institute for Japanese Language and Linguistics. Both
the short-unit and the long-unit list, retrieved 2026-08-11, ver1_0.
  https://clrd.ninjal.ac.jp/bccwj/freq-list.html
  short unit  DOI 10.15084/00003218    long unit  DOI 10.15084/00003212
NINJAL states it is free to use for research and educational purposes. It says
nothing about redistribution, so the list is fetched and never committed —
the handling PLAN.md §2-3 already fixed for JMdict. `wordfreq` was considered and
rejected: its data is CC BY-SA (the same share-alike condition that keeps JMdict
out) and it wants MeCab, which would mean carrying a second tokenizer beside the
one this project claims to use.

TIERS. Boundaries are not chosen, they are read off the corpus: content lemmas
sorted by frequency, cut where the running share of the total reaches
70%, 80%, 90% and 95%. The total is the sum of one frequency per lemma — the
highest, where a lemma appears under several parts of speech — not the raw token
count, which the list does not give per lemma. That lands on cumulative
vocabularies of roughly 1.7k,
3.4k, 8.3k and 15.8k words — near the sizes usually quoted for the JLPT levels,
which is why the README may say the tiers *approximately correspond* to them and
must not say more. Nothing from a textbook or a past paper is ingested (PLAN.md
§2-3).

WHAT THIS CORPUS IS NOT. BCCWJ is WRITTEN Japanese — books, newspapers, white
papers, blogs. This app is about speaking, and everyday spoken vocabulary is
under-represented in it. 天気 lands in tier 2 rather than tier 1 for that reason.
The mapping from learner level to tier below absorbs the shift; it does not undo
it, and the README should say which corpus the tiers came from.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.request
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Final

from config import threshold

DATA_DIR: Final = Path("data/frequency")

# Two lists, because the tokenizer and the frequency data have to agree on what a
# word is. Sudachi is asked for its LONGEST unit so that 会議室 stays one word, and
# the short-unit list does not contain it — a compound looked up by its pieces is
# judged by its rarest piece, which put 会議室 in the top tier by way of 室. The
# long-unit list is the same corpus counted the way the tokenizer counts.
#
# URLs resolved from the DOIs, which redirect over plain HTTP; the resolved
# addresses are recorded so a fetch does not depend on that redirect surviving.
SOURCES: Final[dict[str, tuple[str, str]]] = {
    "suw": (
        "BCCWJ_frequencylist_suw_ver1_0.zip",  # DOI 10.15084/00003218
        "https://repository.ninjal.ac.jp/record/3234/files/BCCWJ_frequencylist_suw_ver1_0.zip",
    ),
    "luw": (
        "BCCWJ_frequencylist_luw_ver1_0.zip",  # DOI 10.15084/00003212
        "https://repository.ninjal.ac.jp/record/3228/files/BCCWJ_frequencylist_luw_ver1_0.zip",
    ),
}
TIER_TABLES: Final[dict[str, Path]] = {
    unit: DATA_DIR / f"tiers_{unit}.json" for unit in SOURCES
}

# The long-unit list holds 2.1 million content lemmas, nearly all of them one-off
# compounds seen once or twice. Only the ones inside the last cut are written out;
# everything past it is rare by definition and is left to the caller to treat as
# unfound. Keeping all of it would be a 100MB table to answer a question that is
# already answered by absence.
_STORE_BEYOND: Final[dict[str, bool]] = {"suw": True, "luw": False}

_CONTENT_POS: Final[tuple[str, ...]] = tuple(threshold("vocabulary_level", "content_pos"))

# Running coverage of all content-word tokens, in order. A word inside the first
# cut is tier 1. Coverage rather than round word counts because a round number is
# a decision and coverage is a measurement — and because the boundary then moves
# with the corpus rather than with whoever edited this file.
COVERAGE_CUTS: Final[tuple[float, ...]] = (0.70, 0.80, 0.90, 0.95)

# Above the last cut. Named so that "tier 4" never appears as a bare number in a
# comparison, since the count of tiers is one more than the count of cuts.
BEYOND: Final = len(COVERAGE_CUTS) + 1

# Which tier each learner level is allowed to reach. The app has three levels and
# the tiers have five bands, so the top band is above every learner by design.
# Calibrated on 2026-08-11 against the DEV half of this project's evaluation set —
# 80 sentences written to be what a beginner would say, 293 content words. 73.7%
# are tier 1 and 91.1% are tier 1 or 2. Mapping beginner to tier 1 would therefore
# call a quarter of the words in a beginner corpus "above the learner's level":
# the check would fire on almost every reply, and the threshold would be blamed
# for a mapping that was wrong. Beginner is tier 2.
#
# Dev only, and this was corrected after the fact. The first calibration used all
# 120 items including the held-out learner sentences AND their reference answers,
# which is a third, unrecorded touch of `test` (docs/ja/glossary.md §7 allows it at
# the start and the end of August, nowhere between). Recomputing on `dev` alone
# gives 73.7% / 91.1% against 76.5% / 91.1%, and the same tier — the decision never
# depended on the held-out half. Which is the point: it cost nothing to take it
# out, so there was no reason to leave it in.
LEVEL_TIER: Final[dict[str, int]] = {
    "beginner": 2,
    "upper_beginner": 3,
    "intermediate": 4,
}


def fetch(unit: str, force: bool = False) -> Path:
    """Download one of the two lists if it is not already here.

    Kept separate from `build` so that a rebuild after changing the cuts does not
    re-download 62MB, and so the network call is one obvious line rather than a
    side effect of asking for a tier.
    """
    name, url = SOURCES[unit]
    archive = DATA_DIR / name
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if archive.exists() and not force:
        return archive
    with urllib.request.urlopen(url) as response:  # noqa: S310 - fixed URL above
        archive.write_bytes(response.read())
    return archive


def build(unit: str) -> dict[str, int]:
    """Read one list and write `lemma -> tier` for its content words.

    Proper nouns are dropped here rather than at lookup: a name has no meaningful
    frequency, and leaving them in would put 田中 in tier 1 and 佐々木 in tier 5
    purely by how often each appears in newspapers.

    Each list is cut against its OWN coverage. A tier from the long-unit table
    means "common among long units", which is the only comparison that makes sense
    for a compound: ranking 会議室 against 猫 in one list would compare things the
    corpus counted differently.
    """
    counts: dict[str, int] = {}
    archive_path = fetch(unit)
    with zipfile.ZipFile(archive_path) as archive, archive.open(archive.namelist()[0]) as raw:
        for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"), delimiter="\t"):
            pos = row["pos"]
            if not pos.startswith(_CONTENT_POS) or pos.startswith("名詞-固有名詞"):
                continue
            try:
                frequency = int(row["frequency"])
            except ValueError:
                continue
            # One lemma can appear under several parts of speech (書き as noun
            # and as verb stem). The most frequent reading is the one a learner
            # is most likely to meet, so it decides the tier.
            if frequency > counts.get(row["lemma"], 0):
                counts[row["lemma"]] = frequency

    ranked = sorted(counts.items(), key=lambda pair: -pair[1])
    total = sum(frequency for _, frequency in ranked)
    keep_beyond = _STORE_BEYOND[unit]
    tiers: dict[str, int] = {}
    running = 0
    cut = 0
    for lemma, frequency in ranked:
        running += frequency
        while cut < len(COVERAGE_CUTS) and running / total > COVERAGE_CUTS[cut]:
            cut += 1
        if cut < len(COVERAGE_CUTS):
            tiers[lemma] = cut + 1
        elif keep_beyond:
            tiers[lemma] = BEYOND

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TIER_TABLES[unit].write_text(json.dumps(tiers, ensure_ascii=False), encoding="utf-8")
    return tiers


@lru_cache(maxsize=len(SOURCES))
def tiers(unit: str = "suw") -> dict[str, int]:
    """A tier table, built on first use.

    Building reads 49MB of TSV for the short units and 521MB for the long ones, so
    it happens once and is cached to disk. A missing table is rebuilt rather than
    raising: the data is deliberately not in the repository, so a fresh clone would
    otherwise fail at the first conversation turn rather than at setup.
    """
    path = TIER_TABLES[unit]
    if path.exists():
        loaded: dict[str, int] = json.loads(path.read_text(encoding="utf-8"))
        return loaded
    return build(unit)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="fetch and rebuild the tier table")
    args = parser.parse_args()
    if not args.build:
        parser.error("nothing to do; pass --build")

    for unit in SOURCES:
        table = build(unit)
        print(f"\n{unit}: {len(table):,} content lemmas -> {TIER_TABLES[unit]}")
        for band in sorted(set(table.values())):
            count = sum(1 for value in table.values() if value == band)
            edge = (
                f"coverage <= {COVERAGE_CUTS[band - 1]:.0%}"
                if band <= len(COVERAGE_CUTS)
                else "beyond the last cut"
            )
            print(f"  tier {band}: {count:>7,} words  ({edge})")


if __name__ == "__main__":
    main()
