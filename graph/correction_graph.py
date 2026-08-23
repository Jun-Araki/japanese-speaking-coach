"""The correction path as a graph: retrieve, correct, validate.

WHY A GRAPH AT ALL, WHEN THREE FUNCTION CALLS WOULD DO. Because the steps are
already separate things with separate failure modes, and the graph is what makes
that visible from outside: a run can be inspected node by node, a node can be
skipped without touching the ones around it, and the validation step is a place in
a diagram rather than an `if` buried in a call chain. It is also the shape the
architecture in the planning document has had since the start — conversation,
correction, retrieval and validation as nodes — so building it as a graph is
keeping a promise rather than adding a dependency.

WHAT IT MUST NOT DO IS CHANGE THE ANSWER. Every published number was measured
through `correction.check_with_retrieval`, and if the graph corrected differently
then the README would describe an engine that is not the one running. So the nodes
call the same functions the measurement calls, in the same order, and
`tests/test_graph.py` pins the two paths to the same output.

RETRIEVAL FAILURE IS NOT CORRECTION FAILURE. The retrieving node catches its own
errors and passes an empty grounding on, because a build without torch still has to
correct sentences — ungrounded, which is exactly what "nothing could be cited"
means.
"""

from __future__ import annotations

import threading
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from correction import Correction, CorrectionResult, validate
from correction.engine import grounding_from, judge


class CorrectionState(TypedDict, total=False):
    """What flows between the nodes.

    The learner's sentence, the scene and the level go in; everything else is
    filled in as the graph runs. `discarded` is carried rather than dropped for the
    same reason the run record carries it: when the validated answer is worse than
    the raw one, the first thing to look at is what the check threw away.
    """

    sentence: str
    scene: str
    level: str
    articles: str
    allowed_ids: set[str]
    result: CorrectionResult
    correction: Correction | None
    validation_reason: str | None
    discarded: str | None


def retrieve(state: CorrectionState) -> dict[str, Any]:
    """Find the sections for this sentence, or return nothing and say so."""
    try:
        from retrieval.index import search

        articles, allowed = grounding_from(search(state["sentence"], scene=state["scene"]))
    except Exception:  # noqa: BLE001 - a build without retrieval still corrects
        articles, allowed = "", set()
    return {"articles": articles, "allowed_ids": allowed}


def correct(state: CorrectionState) -> dict[str, Any]:
    """Ask the model, with whatever the retrieving node found in front of it."""
    result = judge(
        state["sentence"],
        state["scene"],
        state["level"],
        grounding=(state.get("articles", ""), state.get("allowed_ids", set())),
    )
    return {"result": result, "correction": result.correction}


def check(state: CorrectionState) -> dict[str, Any]:
    """Run the deterministic checks over the answer.

    Check 3 is not here. It was measured against a bar written before either of its
    predicates existed and failed on both, so it does not ship — and an app running
    a check the measurements rejected would be an app doing something the README
    does not describe.
    """
    correction = state.get("correction")
    if correction is None:
        return {"validation_reason": None, "discarded": None}

    checked = validate(state["sentence"], correction)
    return {
        "correction": checked.correction,
        "validation_reason": checked.reason,
        "discarded": None if checked.discarded is None else checked.discarded.corrected_sentence,
    }


def build() -> Any:
    """Compile the graph. Called once; the result is safe to reuse."""
    builder: StateGraph[CorrectionState, None, CorrectionState, CorrectionState] = StateGraph(
        CorrectionState
    )
    builder.add_node("retrieve", retrieve)
    builder.add_node("correct", correct)
    builder.add_node("validate", check)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "correct")
    builder.add_edge("correct", "validate")
    builder.add_edge("validate", END)
    return builder.compile()


_GRAPH: Any = None

# BUILT ONCE EVEN WHEN TEN CALLERS ARRIVE TOGETHER. Since 2026-08-22 the screen
# corrects a whole conversation at once, ten threads at a time, and every one of them
# finds `_GRAPH` empty and builds one. Nothing is corrupted by that — each gets a
# working graph and the last assignment wins — but it is nine compilations nobody
# asked for on the one call the learner is watching a spinner for.
_BUILDING = threading.Lock()


def graph() -> Any:
    global _GRAPH
    with _BUILDING:
        if _GRAPH is None:
            _GRAPH = build()
        return _GRAPH


def run(sentence: str, scene: str, level: str) -> CorrectionState:
    """One sentence through the whole path."""
    state: CorrectionState = {"sentence": sentence, "scene": scene, "level": level}
    return graph().invoke(state)  # type: ignore[no-any-return]
