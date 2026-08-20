"""The HTTP layer: three endpoints, and nothing that keeps anything.

POST /chat   one turn of conversation
POST /check  one sentence corrected, through the graph
GET  /health what this build can actually do

NOTHING IS STORED. No database, no file, no log line carrying a learner's sentence.
That is a design decision rather than an omission (the planning document, §2-5): the
sentences are personal data, there are two or three testers, and a usage log of that
size is not a statistic worth taking responsibility for. The history a conversation
needs is held by the caller and sent with each request, which is what makes the
server stateless as a consequence rather than as a claim.

/health REPORTS WHAT IS MISSING. The published build may ship without retrieval —
the free tier may not take torch — and a health check that says "ok" while the
grounding is silently gone would hide exactly the failure that matters. It answers
whether the index can be built, not whether the process is alive.

THE STREAMLIT APP DOES NOT CALL THIS. It cannot: Streamlit Community Cloud runs one
process from one entry file, so the deployed app calls the graph in the same
process. This layer is what runs under Docker and what the endpoints above are for;
both paths go through the same graph, so neither can drift into behaving
differently from the other.
"""

from __future__ import annotations

from typing import Any, Final

from fastapi import FastAPI
from pydantic import BaseModel, Field

from correction.engine import GROUNDED_PROMPT_VERSION
from dialogue import LEVELS, SCENES, Utterance, opening_line, reply
from dialogue.reply import Speaker
from graph.correction_graph import run as run_correction
from llm import active_model_name

# One session's worth of turns. The cap is here rather than in the app because the
# app is not the only caller — and a cap that lives in the caller is not a cap.
MAX_TURNS: Final = 20

app = FastAPI(
    title="Japanese Speaking Coach",
    summary="Speaking practice for beginners, corrected after the conversation",
)


class Turn(BaseModel):
    # Literal rather than str: an unknown speaker is rejected at the edge with a 422
    # instead of reaching the conversation prompt as a role nobody defined.
    speaker: Speaker
    text: str


class ChatRequest(BaseModel):
    scene: str
    level: str
    history: list[Turn] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str


class CheckRequest(BaseModel):
    sentence: str
    scene: str
    level: str


class CheckResponse(BaseModel):
    """What the learner is shown, plus what the checks did.

    `needs_correction` can be false with a `discarded` sentence attached: that is a
    correction the validation node threw away, and it is reported rather than
    hidden so a bad check can be seen from outside instead of only in a run record.
    """

    needs_correction: bool
    corrected_sentence: str | None
    reason_en: str | None
    grounding_ids: list[str]
    validation_reason: str | None
    discarded: str | None
    attempts: int


@app.get("/health")
def health() -> dict[str, Any]:
    """What this build can do, not merely that it is running."""
    retrieval: dict[str, Any] = {"available": False, "reason": None, "version": None}
    try:
        from retrieval.index import RETRIEVAL_VERSION, collection

        collection()
        retrieval = {"available": True, "reason": None, "version": RETRIEVAL_VERSION}
    except Exception as exc:  # noqa: BLE001 - the reason is the point of the field
        retrieval["reason"] = f"{type(exc).__name__}: {exc}"[:200]

    return {
        "status": "ok",
        "model": active_model_name(),
        "prompt_version": GROUNDED_PROMPT_VERSION,
        "retrieval": retrieval,
        "scenes": sorted(SCENES),
        "levels": sorted(LEVELS),
        "max_turns": MAX_TURNS,
        "stores_anything": False,
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """One reply from the partner. An empty history gets the opening line."""
    if not request.history:
        return ChatResponse(reply=opening_line(request.scene))

    history = [Utterance(turn.speaker, turn.text) for turn in request.history[-MAX_TURNS * 2 :]]
    return ChatResponse(reply=reply(request.scene, request.level, history))


@app.post("/check", response_model=CheckResponse)
def check(request: CheckRequest) -> CheckResponse:
    """One sentence through retrieve, correct and validate."""
    state = run_correction(request.sentence, request.scene, request.level)
    correction = state.get("correction")
    result = state["result"]

    if correction is None:
        # The model never produced a usable answer. Reported as "nothing to correct"
        # rather than as an error, because that is what the learner is shown, and
        # `attempts` is what says it was tried twice.
        return CheckResponse(
            needs_correction=False,
            corrected_sentence=None,
            reason_en=None,
            grounding_ids=[],
            validation_reason=None,
            discarded=None,
            attempts=result.attempts,
        )

    return CheckResponse(
        needs_correction=correction.needs_correction,
        corrected_sentence=correction.corrected_sentence,
        reason_en=correction.reason_en,
        grounding_ids=list(correction.grounding_ids),
        validation_reason=state.get("validation_reason"),
        discarded=state.get("discarded"),
        attempts=result.attempts,
    )
