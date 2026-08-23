"""Every learner sentence, checked in one go once the conversation is over.

WHERE THIS USED TO RUN, AND WHY IT MOVED. The rule has always been that nothing is
corrected while the learner talks -- the review screen exists because a beginner
interrupted mid-sentence stops talking. The rule was kept on screen and broken
underneath it: the correction call was made on the turn, inline, so the learner
waited for a result that was deliberately not shown to them. Measured on
2026-08-21, a turn took 14.08s and 4.78s of it was this. Moving the whole batch to
the end is not a new principle; it is the existing one finally being implemented.

TEN AT A TIME, AND NOT ONE MORE. Five sentences checked one after another take
23.39s; the same five in parallel take 7.74s, so the width pays for itself. Width
without a ceiling does not: enough simultaneous calls invite a 429, and a 429 does
not make the corrections slow, it makes them missing. The learner is watching a
spinner at this point and would rather wait than lose the answers.

THE CEILING WAS FIVE ON A GUESS AND IS TEN ON A MEASUREMENT. Five was chosen because
more looked likely to be refused. Measured on 2026-08-22: thirty simultaneous
corrections all succeeded, in the same wall time as fifteen. The limit that is
actually tight in this app belongs to the speech model, not to this one. Ten is still
a ceiling and still well under what was shown to work, because "it held at thirty on
a quiet afternoon, from one process" is not "it holds while a room is using it".

WHO THAT HELPS: nobody with five sentences, which already run at once. Somebody with
ten, which was two rounds and about fifteen seconds of waiting after they pressed the
button, and is now one round.

ORDER IS THE ORDER THEY SPOKE IN. `executor.map` yields by input position rather
than by completion, so the review lists the sentences the way the conversation
went. A review sorted by whichever call finished first would be a review the
learner cannot follow back.

ONE FAILURE IS ONE GAP, NOT FIVE. A sentence whose correction fails comes back
with nothing attached instead of vanishing, so the review can say it could not be
checked -- and so "You said N sentences" counts what was actually said.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Final

from correction import CorrectionResult
from graph.correction_graph import run as run_correction

MAX_CORRECTION_WORKERS: Final = 10


def correct_one(sentence: str, scene: str, level: str) -> CorrectionResult:
    """Judge one learner sentence, or record that it could not be judged.

    Nothing raised in here reaches the caller. This runs inside a worker, on a
    batch that is one press away from the review screen, and an exception escaping
    one sentence would take the rest of the batch down with it.
    """
    try:
        # Through the graph, which is also what the API calls: retrieve, correct,
        # validate. Two paths into one graph rather than two copies of the same
        # three steps -- a screen that corrects differently from the endpoint is a
        # screen the measurements do not describe.
        state = run_correction(sentence, scene, level)
        return replace(state["result"], correction=state.get("correction"))
    except Exception:  # noqa: BLE001 - a failed check is a gap in the review, not a crash
        return CorrectionResult(sentence, correction=None, attempts=0, format_problems=())


def correct_all(sentences: list[str], scene: str, level: str) -> list[CorrectionResult]:
    """Check the whole conversation, a few sentences at a time, in spoken order."""
    if not sentences:
        return []
    # No more threads than there are sentences: a pool of ten for one sentence is
    # nine threads started to do nothing.
    workers = min(MAX_CORRECTION_WORKERS, len(sentences))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="correction") as pool:
        return list(pool.map(lambda sentence: correct_one(sentence, scene, level), sentences))
