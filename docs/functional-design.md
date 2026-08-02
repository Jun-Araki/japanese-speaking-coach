# Functional Design

> **Thin by design.** Structure and data shapes only, filled in here as implementation
> settles them.

## System diagram

```mermaid
graph TB
    U[Learner] -->|voice| ST[Streamlit single page]
    ST -->|REST + access code| API[FastAPI]
    API --> G[LangGraph]

    subgraph G [LangGraph]
        DLG[Dialogue node]
        COR[Correction node]
        RET[Retrieval node]
        VAL[Validation node]
        DLG -.parallel.- COR
        RET --> COR
        COR --> VAL
        VAL -->|reject, once| COR
    end

    DLG --> TTS[Text to speech]
    COR --> DB[(PostgreSQL)]
    RET --> CH[(Chroma)]
    VAL --> NLP[SudachiPy tokenizer]
    ST --> STT[Transcription]
```

## Screen flow

One page only. It switches between two states; no second page is ever added.

```
Scene + level select ──▶ Conversation (record ▸ reply ▸ repeat) ──▶ Review
                                        ▲                 │
                                        └── "Say again" ───┘
```

- The learner's own transcribed sentence is **always** shown, with a **Say again** button
  (never make them retype). The count of presses is a proxy for transcription quality.
- Only the **AI's** reply text can be hidden; hiding it turns the session into listening
  practice. Which mode was used is recorded.
- Corrections never interrupt the conversation. The correction node runs every turn in the
  background and results appear only in the review.

## Core flow: why this is not a thin wrapper

The correction is emitted as **structured output** and then checked by deterministic Python
in the validation node:

1. **Rewrite-too-far check** — if the edit distance between the original and the corrected
   sentence exceeds the threshold, it is a different sentence, not a correction; discard it.
2. **Vocabulary level check** — tokenize the AI reply and regenerate if it contains too
   many words above the learner's level.
3. **Over-correction suppression** — if no grounding was retrieved and the original sentence
   is already natural, fall back to "no correction needed".

This is what the baseline comparison is designed to prove: the naive single-call
implementation is measured on the same data, and the two are reported side by side.

## Data structures

### Evaluation item (`data/evaluation/*.json`) — the primary public artefact

```json
{
  "id": "eval-001",
  "scene": "greeting",
  "learner_sentence": "おはようです",
  "needs_correction": true,
  "corrected_sentence": "おはようございます",
  "reason_en": "The polite morning greeting is a fixed phrase.",
  "split": "dev"
}
```

`needs_correction: false` items carry no `corrected_sentence` or `reason_en`. The set is
90 items needing correction and 30 already-natural items, so over-correction is measurable.

### Correction result (structured output of the correction node)

```json
{
  "needs_correction": true,
  "corrected_sentence": "おはようございます",
  "reason_en": "The polite morning greeting is a fixed phrase.",
  "grounding_ids": ["grammar-003"]
}
```

Errors are **not categorised** by type (particle, conjugation, …). Beginners do not need it
and it makes both implementation and evaluation heavier.

### Session and turn (PostgreSQL)

- `session` — access code, scene, level, AI-text-shown flag, consent flag, timestamps
- `turn` — session id, transcript, say-again count, correction result, latency split into
  speech and non-speech, token counts

No learner name is stored. Audio is retained only for the September transcription study.

## Evaluation is measured in two stages

The system is speech→text and then text→correction. Measuring only end to end cannot tell
which stage failed — transcription silently repairs learner mistakes, which makes a correct
correction engine look wrong.

| What | How | When |
|---|---|---|
| Correction engine | Evaluation script feeds the 120 items **as text, bypassing the app** | August |
| Transcription | 30 tester recordings transcribed by ear by a native speaker, compared to machine output | September |
| End to end | Same sentences through both paths; the difference is what transcription erased | September |

The README must state plainly that correction numbers are measured on text.
