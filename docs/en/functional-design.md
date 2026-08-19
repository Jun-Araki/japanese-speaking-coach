# Functional Design

**Translation of [`../ja/functional-design.md`](../ja/functional-design.md), which is authoritative.** If the two
disagree, the Japanese version is correct and this file needs updating.


> **Thin by design.** Structure and data shapes only, filled in here as implementation
> settles them.

## System diagram

```mermaid
graph TB
    U[Learner] -->|voice| ST[Streamlit single page]
    ST -->|REST + shared access code| API[FastAPI]
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
    COR --> RV[Review screen, in memory only]
    RET --> CH[(Chroma)]
    VAL --> NLP[SudachiPy tokenizer]
    ST --> STT[Transcription]
```

**Nothing is persisted (decided 2026-08-16).** Corrections were originally written to
PostgreSQL; **nothing a learner says, records or gets corrected is stored anywhere** now
(see "The decision to store nothing" in [architecture.md](architecture.md)). Corrections live
in `st.session_state` for the length of the session and **disappear when the tab closes**.
Chroma is a read-only index and holds no learner data.

## Screen flow

One page only. It switches between three states; no second page is ever added.

```
Scene + level select ──▶ Conversation (record ▸ reply ▸ repeat) ──▶ Review
        ▲                              ▲                 │           │
        │                              └── "Say again" ───┘           │
        └──────────────── "Start another conversation" ───────────────┘
```

The state is decided by which keys exist in `st.session_state`: `scene` means conversation,
`review` means review, neither means selection. **Corrections accumulate during the
conversation but are never rendered outside the review.**

- The learner's own transcribed sentence is **always** shown, with a **Say again** button
  (never make them retype). ~~The count of presses is a proxy for transcription quality.~~
  → **Nothing is stored, so it cannot be counted** (2026-08-16). The button stays: its purpose
  is sparing the learner from retyping, not producing a metric.
- Only the **AI's** reply text can be hidden; hiding it turns the session into listening
  practice. ~~Which mode was used is recorded.~~ → **Not recorded** (same reason).
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
91 items needing correction and 29 already-natural items, so over-correction is measurable.
(It was 90/30 until eval-052 was relabelled on 2026-08-13; the data is authoritative and
`tests/test_evaluation_items.py` pins it.)

### Correction result (structured output of the correction node) — fixed 2026-08-04

```json
{
  "needs_correction": true,
  "corrected_sentence": "おはようございます",
  "reason_en": "The polite morning greeting is a fixed phrase.",
  "grounding_ids": ["grammar-003"]
}
```

| Key | Type | Content |
|---|---|---|
| `needs_correction` | boolean | Required. Anything other than a boolean counts as a format failure |
| `corrected_sentence` | string \| null | Required when `needs_correction` is true. **Repairs the sentence they wrote**; it is not a better sentence of the model's own |
| `reason_en` | string \| null | Same. **One or two sentences of English.** Japanese quoted inside 「」 to point at a word is allowed |
| `grounding_ids` | array of string | **Always empty until retrieval lands on 30 August** (changed from "until week 2" to "early September" on 2026-08-16, then pulled forward with the schedule on 2026-08-18). **The key is carried from the start** — adding it later would mean rebuilding stored data |

When `needs_correction` is false, `corrected_sentence` and `reason_en` are **normalised to
null**. A sentence judged not to need changing has nothing to show, whatever the model chose
to put there.

Errors are **not categorised** by type (particle, conjugation, …). Beginners do not need it
and it makes both implementation and evaluation heavier.

**This JSON is parsed by us.** Provider-side constrained decoding (`with_structured_output`,
`responseSchema`) is deliberately not used: it would make the JSON half of
`format_compliance_rate` true by construction, **reporting as measured something that was
never measured.** It also keeps the baseline and the real implementation on one parsing path,
so there is only one scoring code path.

### Correction call result — what the evaluation script counts

One call to the correction engine returns the correction itself plus **what is needed to count
format compliance**. Without it the denominator of `format_compliance_rate` cannot be built.

| Field | Content |
|---|---|
| `learner_sentence` | The sentence that was judged |
| `correction` | The structured output above. **Empty when both attempts were malformed** — meaning unjudgeable, not "no correction needed" |
| `attempts` | 1, or 2 when it was retried |
| `format_problems` | Any of `invalid_json` / `reason_not_english`. Empty means compliant |

**`format_problems` describes the first attempt.** A retry that succeeded leaves it
non-compliant — if a retry could erase a format failure, **that is the same lie as dropping
the malformed cases from the denominator.** The correction itself may come from the retry
(accuracy and format are recorded separately, per glossary §5).

### Session and turn — **not persisted (revised 2026-08-16)**

~~A `session` table and a `turn` table in PostgreSQL.~~ → **No tables. No database.**

Session state lives in `st.session_state` and nowhere else.

| Key | Contents |
|---|---|
| `scene` / `level` | The chosen scene and level. **Their presence means "in conversation"** (this drives the screen flow) |
| `show_ai_text` | Whether the AI's reply text is shown |
| `turns` | The sequence of transcripts and AI replies |
| `corrections` | Correction results accumulated in the background each turn. **Never rendered outside the review** |
| `review` | **Its presence means "in review"** |

**Closing the tab erases all of it.** No learner name, no utterance, no audio, no correction
result survives. **Latency, token counts and Say-again presses are not recorded either** (see
"What is deliberately not measured" in [product-requirements.md](product-requirements.md)).

**The per-day token and text-to-speech caps are the one exception.** They exist to bound cost,
so they are held **in-process as counters that identify nobody** — who used the app is not kept.

## Error handling

**Principle: a failure in correction never stops the conversation.** Corrections are shown
after the session, so a background failure is survivable. **A failure in the conversation is
never hidden**, however — when the AI goes silent, learners assume their pronunciation was
at fault.

| Failure | Behaviour |
|---|---|
| Transcription fails or returns empty | Show "I could not hear that" in English and prompt **Say again**. Not recorded as a turn |
| Correction JSON is malformed | **Retry once.** If still malformed, omit that sentence from the review — but **always count it in the denominator of `format_compliance_rate`** (hiding failures makes format compliance look better than it is) |
| How that retry is sent | **Send the first output back with what was wrong with it.** The correction runs at `temperature = 0`, so resending the same prompt returns the same malformed output and **the retry would be a retry in name only** |
| Reason comes back in Japanese | Use the output, but count it as non-compliant in `format_compliance_rate`. Accuracy metrics are unaffected. **Not retried** — the judgement is sound, only the language is wrong |
| Reason quotes Japanese inside it | Counts as compliant. "「は」 marks the topic" is how a particle gets explained, and a naive "contains Japanese, therefore non-compliant" rule **rejects the best reasons first**. Quoted spans are removed before the check |
| The correction call itself fails (API error) | **The conversation continues.** The sentence is recorded as unjudgeable and does not appear in the review as a correction |
| Unjudgeable sentences in the review | **Show the count** ("1 sentence could not be checked"). Dropping them silently reads as "these were fine", which is the one thing they are **not** known to be |
| Dialogue API error | Show an error and a retry button. **Never paper over it with a canned reply** — the learner must not think the AI simply ignored them |
| Still over level after regeneration | Use the reply as-is (one regeneration only) and record it as non-compliant in `level_compliance_rate` |
| Retrieval returns nothing | Treat as ungrounded: **state nothing as certain in the reason**, and if the original sentence is already natural, fall back to "no correction needed" |
| Recording exceeds the length cap | Show the cap before recording; anything beyond it is not sent |
| Daily token or TTS cap reached | **Block the start of a new conversation** and explain in English when it resets. Never cut off a conversation in progress |
| ~~Database write fails~~ | **Cannot happen (2026-08-16).** There is no database, so this row is gone |

**Counting format failures matters most.** Silently discarding malformed output inflates
`format_compliance_rate` and **makes the evaluation itself dishonest.**

## Evaluation is measured in two stages

The system is speech→text and then text→correction. Measuring only end to end cannot tell
which stage failed — transcription silently repairs learner mistakes, which makes a correct
correction engine look wrong.

| What | How | When |
|---|---|---|
| Correction engine | Evaluation script feeds the 120 items **as text, bypassing the app** | **Measured** |
| ~~Transcription~~ | ~~30 tester recordings transcribed by ear, compared to machine output~~ | **Not measured (2026-08-16)** |
| ~~End to end~~ | ~~Same sentences through both paths; the difference is what transcription erased~~ | **Not measured (2026-08-16)** |

**The speech stage goes unmeasured because audio is not stored**, so the material does not
exist. **The analysis above is still correct**, which is exactly why the README carries it as
a warning:

> **Correction figures are measured on text. The speech stage is not measured, so real accuracy
> when speaking is lower than these numbers.**

**Saying what was not measured is stronger than pretending it was.** This is the first thing
to restore when there is time again.
