"""The vector index over the grammar reference, and the search that reads it.

BUILT AT STARTUP, IN MEMORY. The corpus is eight files and thirty-six sections,
which embed in about a second once the model is loaded, so there is nothing to gain
from persisting it — and a persisted index has a failure this one cannot have: it
goes stale. An article edited without the index being rebuilt would leave the app
citing a paragraph that no longer says what it says, and nothing in the output would
show it. `CHROMA_PERSIST_DIR` is therefore read by nothing here.

THE PREFIXES ARE NOT DECORATION. The e5 models are trained with "query: " on the
question side and "passage: " on the document side, and omitting them degrades
retrieval quietly — the search still returns three articles in some order, and the
only symptom is a hit rate that is worse than it should be for no visible reason
(.env.example says the same thing next to EMBEDDING_MODEL).

THE MODEL IS LOADED ONCE. Several hundred megabytes of weights, so a module-level
cache rather than a load per call; the first search pays for it and the rest do not.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from threading import RLock
from typing import TYPE_CHECKING, Any, Final

from config import threshold
from retrieval.chunks import Chunk, load_chunks

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from sentence_transformers import SentenceTransformer

# Bumped whenever anything changes what the search returns for the same sentence —
# the chunking, the query text, the model. Neither `prompt_version` nor
# `thresholds_digest` can carry it: improvement cycle 2 changed only the query text,
# which is code, and without this the two run records either side of it would differ
# in their numbers and in nothing that explains why.
#
# v1: sentence alone. v2 (2026-08-20): the scene's politeness tier prepended.
RETRIEVAL_VERSION: Final = "retrieval-v2"

DEFAULT_MODEL: Final = "intfloat/multilingual-e5-small"
COLLECTION: Final = "grammar"

# Cosine, so a score is a similarity in roughly [0, 1] and `score_min` can be read
# as "how alike is alike enough". Chroma reports distance, and the conversion back
# to similarity happens in one place here rather than at every call site.
SPACE: Final = "cosine"

QUERY_PREFIX: Final = "query: "
PASSAGE_PREFIX: Final = "passage: "


@dataclass(frozen=True)
class Result:
    """One retrieved section, with the article it belongs to and how close it was."""

    chunk_id: str
    article_id: str
    heading: str
    body: str
    score: float


def model_name() -> str:
    return os.environ.get("EMBEDDING_MODEL", DEFAULT_MODEL)


# ONE LOCK FOR BOTH LOADS, HELD ACROSS THE CACHE LOOKUP. `lru_cache` decides whether
# it has an answer BEFORE any lock inside the function body can be taken, so five
# threads calling `search()` for the first time all miss, all enter, and all load. That
# stopped being hypothetical when the corrections started running in parallel: several
# hundred megabytes of weights loaded five times is wasted seconds here and no memory
# left on Community Cloud. Wrapping the cached function in a plain one that takes the
# lock first means the threads behind the first one find the cache already filled.
#
# REENTRANT, NOT PLAIN. `collection()` calls `embed_passages()` which calls `_model()`,
# so one thread takes this lock twice; a `Lock` would deadlock every time.
#
# It replaces the `Lock` added on 2026-08-21, when the container's own health check
# built the collection twice and the second build failed with "Collection [grammar]
# already exists". That lock sat inside the function body and so never covered the
# lookup — but the reason it is a lock at all has not changed: two people opening the
# app at the same moment is what a meetup looks like.
_INIT_LOCK: Final = RLock()


@lru_cache(maxsize=1)
def _load_model() -> SentenceTransformer:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name())


def _model() -> SentenceTransformer:
    with _INIT_LOCK:
        return _load_model()


def embed_passages(chunks: list[Chunk]) -> list[list[float]]:
    """Vectors for the corpus side, with the passage prefix applied."""
    texts = [PASSAGE_PREFIX + chunk.embedding_text for chunk in chunks]
    return [list(map(float, vector)) for vector in _model().encode(texts)]


# One short line per politeness tier, prepended to the query. Keyed on the TIER
# LETTER — the first element of the POLITENESS_FLOORS tuple — so this is three
# strings for three tiers and quotes no evaluation item.
#
# The long requirement text from `politeness_floor` was tried first and was worse
# than useless: several sentences of English against a ten-character learner
# sentence swamped the query, and grammar-008 came back first for every item in the
# sample. Length is the whole difference between the two attempts.
_TIER_CUE: Final[dict[str, str]] = {
    "A": "casual speech is acceptable.",
    "B": "the sentence must end politely.",
    "C": "です・ます throughout.",
}


def query_text(sentence: str, scene: str | None) -> str:
    """What is actually embedded on the query side.

    IMPROVEMENT CYCLE 2 (2026-08-20): the scene's politeness tier is prepended.
    Diagnosed on the threshold block only — the twenty measurement items were not
    looked at, before or after — where the sentence alone could not reach the right
    article for a whole class of item. 「タクシーで行く。」 needs the politeness
    article and every cue in the sentence points at the particle 「で」 instead: the
    politeness floor is a property of WHO IS BEING SPOKEN TO, so it is not in the
    sentence at all, and no amount of ranking over the sentence can recover it.

    Three formulations were tried on that block, and the differences between them
    are recorded rather than only the winner: the sentence alone reached 5 of 8,
    the full requirement paragraph also 5 of 8 (different items), and this one 7 of
    8. Trying three and reporting one would make a tuned choice look like a first
    guess.
    """
    if scene is None:
        return QUERY_PREFIX + sentence
    from dialogue.scenes import politeness_floor

    tier, _ = politeness_floor(scene)
    return f"{QUERY_PREFIX}{_TIER_CUE[tier]} {sentence}"


def embed_query(sentence: str, scene: str | None = None) -> list[float]:
    """The vector for one learner sentence, with the query prefix applied."""
    return [float(value) for value in _model().encode(query_text(sentence, scene))]


@lru_cache(maxsize=1)
def _build_collection() -> Any:
    import chromadb

    client = chromadb.EphemeralClient()
    # get_or_create, not create: under the lock this cannot race, and without the
    # idempotent call a retry after any failure would hit a half-built collection
    # and report "already exists" instead of whatever actually went wrong.
    store = client.get_or_create_collection(name=COLLECTION, metadata={"hnsw:space": SPACE})
    if store.count():
        return store

    chunks = load_chunks()
    store.add(
        ids=[chunk.id for chunk in chunks],
        embeddings=embed_passages(chunks),  # type: ignore[arg-type]
        documents=[chunk.body for chunk in chunks],
        metadatas=[{"article_id": chunk.article_id, "heading": chunk.heading} for chunk in chunks],
    )
    return store


def collection() -> Any:
    """The index, built once on first use and kept for the life of the process.

    Serialised on `_INIT_LOCK`, for the reason written above it: the build is a model
    load and 36 embeddings, and whatever arrives during it has to wait rather than
    start a second one.
    """
    with _INIT_LOCK:
        return _build_collection()


def search(sentence: str, top_k: int | None = None, scene: str | None = None) -> list[Result]:
    """The sections closest to one learner sentence, best first.

    `top_k` defaults to the configured 3 — the same 3 `retrieval_hit_rate` is
    measured over. NOTHING IS FILTERED HERE. `score_min` decides whether a result
    counts as grounding, and applying it inside the search would make the published
    hit rate move with the threshold, which config/thresholds.toml explicitly
    forbids: a hit rate that moves with score_min could be tuned through it with
    nothing in the repository showing that it had been.
    """
    limit = threshold("retrieval", "top_k") if top_k is None else top_k
    found = collection().query(
        query_embeddings=[embed_query(sentence, scene)],
        n_results=limit,
        include=["documents", "metadatas", "distances"],
    )
    results: list[Result] = []
    for chunk_id, document, metadata, distance in zip(
        found["ids"][0],
        found["documents"][0],
        found["metadatas"][0],
        found["distances"][0],
        strict=True,
    ):
        results.append(
            Result(
                chunk_id=chunk_id,
                article_id=str(metadata["article_id"]),
                heading=str(metadata["heading"]),
                body=document,
                score=1.0 - float(distance),
            )
        )
    return results


def grounding_article_ids(results: list[Result], score_min: float) -> tuple[str, ...]:
    """The articles a correction may cite, in rank order and without repeats.

    Sections are what the index holds and articles are what a learner is shown, so
    the reduction happens here. Two sections of the same article count once: a
    citation list that names one article twice tells the learner nothing and makes
    a grounded correction look better supported than it is.
    """
    seen: list[str] = []
    for result in results:
        if result.score >= score_min and result.article_id not in seen:
            seen.append(result.article_id)
    return tuple(seen)
