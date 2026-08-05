# Glossary — Ubiquitous Language

**Translation of [`../ja/glossary.md`](../ja/glossary.md), which is authoritative.** If the two
disagree, the Japanese version is correct and this file needs updating.


This file is not documentation of the code. **It is the labelling standard for the 120-item
evaluation set and the definition of every number published in the README.**

If these definitions shift after labelling starts, previously labelled items become
inconsistent and the evaluation is worthless. **Change this file only deliberately, and
re-check already-labelled items when you do.**

---

## 1. Core domain terms

| Term | Japanese | Definition | Code identifier |
|---|---|---|---|
| **Scene** | 場面 | The situation the learner practises in. Fixed list, see §3 | `scene` |
| **Level** | レベル | The learner's declared proficiency tier. Fixed list, see §4 | `level` |
| **Turn** | ターン | One learner utterance plus the AI reply to it | `turn` |
| **Session** | 会話セッション | Everything between "Start conversation" and "End conversation" | `session` |
| **Review** | 振り返り | The screen shown after a session, listing every correction | `review` |
| **Correction** | 訂正 | A judgement about one learner sentence: whether it should be changed, and if so how | `correction` |
| **Natural phrasing** | 自然な言い方 | The corrected sentence a native speaker would use in that scene | `corrected_sentence` |
| **Reason** | 理由 | One or two sentences in English explaining the correction | `reason_en` |
| **Grounding** | 根拠 | A grammar reference article cited as support for a reason | `grounding_ids` |
| **Say again** | もう一度 | Re-recording because transcription got it wrong. Never retyping | `say_again_count` |

**Never used as synonyms in code or UI:** feedback, suggestion, fix, error, mistake.
There is exactly one word for each concept above.

---

## 2. The labelling decision — the single most important definition

Every evaluation item and every model output carries **one binary label**:

### `needs_correction: true` (NG)

The sentence should be changed before a learner says it to a Japanese person in this scene.

Label `true` when the sentence is:

- **Grammatically wrong** — wrong particle, wrong conjugation, missing obligatory element
- **Wrong politeness for the scene** — plain form to a superior, or stiff honorifics to a friend
- **Not what a native speaker would say**, even if grammatical (unnatural collocation,
  literal translation from English)
- **A non-existent fixed phrase** — e.g. an invented variation of a set greeting

### `needs_correction: false` (OK)

Label `false` when a native speaker would accept the sentence as-is in this scene, **even if
a more elegant phrasing exists.** This is the harder judgement and the one that matters:
these 30 items exist solely to measure over-correction.

Explicitly label `false` for:

- **Simple but correct sentences.** A beginner sentence is not wrong for being plain
- **Regional or casual variants** that are genuinely used
- **Sentences a native would not remark on**, even if the author personally prefers another form

### The politeness floor — set by who is listening (decided 2026-08-05)

Judging that the **politeness is wrong for the scene** requires knowing how casual the
sentence is allowed to be. Without that, the same plain-form sentence gets labelled `true`
in one item and `false` in another, and `detection_accuracy` and `over_correction_rate`
both become a measure of which way the labeller happened to lean. The first 60 candidates
did exactly this, which is why it is fixed here.

**What sets the floor is the listener, not the scene.** 「トイレはどこ？」 is fine said to a
colleague and needs correcting said to a shop assistant.

| Tier | Listener | Floor | Scenes |
|---|---|---|---|
| **A** | A neighbour, a colleague | No polite marker needed | `greeting` `thanks` |
| **B** | Someone just met, a shop assistant | **At least one of お / ください / です / ます** | `self_introduction` `simple_request` |
| **C** | A colleague kept waiting, a manager | **です・ます required** | `delay_notice` `workplace_keigo` |

- **The floor at B is one polite marker, not a fully polite sentence.** 「これ、ください」 and
  「お名前は」 clear it and are `false`. 「トイレはどこ？」 and 「名前は？」 have none and are `true`
- **Plain form is `true` at C** because, as in §3, these are the scenes where controlling
  politeness actually starts to matter
- **At A, politeness alone is never a reason to label `true`.** There, `true` comes only from
  a grammatical error, a phrasing no native speaker would use, or an altered fixed phrase
- **A fixed phrase aimed in the wrong direction is a misused fixed phrase, not a politeness
  level.** Saying 「ご苦労さまです」 to a superior is `true` at tier A too
- **C asks for です・ます, not for full honorific and humble forms.** 「少し考えます」 to a manager
  is `false`
- **「あなた」 is never itself a reason to label `true`** (decided during verification on
  2026-08-05). What actually reads as unnatural is usually the word order or the literal
  translation, and that is what the reason should name. 「あなたはこの本を持っていますか」 is `false`

### Rule when uncertain

**If you hesitate, label `false` and write the item's uncertainty in a note.** The system is
designed to under-correct rather than over-correct, and a mislabelled `true` item silently
rewards over-correction. Do not create items whose label you cannot defend to a second
native rater.

### Not part of the label

- **Error type is never recorded.** No particle / conjugation / vocabulary categorisation.
  Beginners do not need it, and it makes labelling and scoring heavier for no gain.
- **Pronunciation is never judged.** Voice is an input method only.

---

## 3. Scenes

Ordered by difficulty. Beginners are not expected to reach the later ones.

| `scene` | Japanese | Notes |
|---|---|---|
| `greeting` | 挨拶 | Entry point. Everyone starts here |
| `self_introduction` | 自己紹介 | Name, work, where you are from |
| `thanks` | お礼 | |
| `simple_request` | 簡単な依頼 | |
| `delay_notice` | 予定と遅れの連絡 | First scene requiring real politeness control |
| `workplace_keigo` | 職場の敬語 | Ceiling. Where the Japan–India bridge experience connects |

**The learner always speaks their own words.** Scenes may be made easier; the sentences the
learner produces are never turned into multiple choice. Choosing from fixed phrases would
leave nothing to correct and would destroy the evaluation, which is the point of the project.

---

## 4. Levels

| `level` | Label shown to the user | Roughly corresponds to |
|---|---|---|
| `beginner` | Beginner | JLPT N5 |
| `upper_beginner` | Upper beginner | JLPT N4 |
| `intermediate` | Intermediate | JLPT N3 |

**"Roughly corresponds to" is deliberate wording.** JLPT past papers and commercial textbooks
are never ingested. Difficulty tiers are derived from word frequency in SudachiDict, so the
mapping is an approximation and the README says so.

**Over-level word** (`over_level_word`): a token in the **AI's reply** whose frequency tier
is above the learner's declared level. Detected by tokenizing with SudachiPy — string
matching cannot find word boundaries in Japanese, which is why morphological analysis is
required rather than decorative.

---

## 5. Metric definitions

All correction metrics are measured by feeding evaluation items **as text directly to the
correction engine**, bypassing the app, the microphone, and transcription.

| Metric | `identifier` | Definition | August target |
|---|---|---|---|
| Detection accuracy | `detection_accuracy` | Of the 90 items labelled `true`, the share the system also judged `true` | ≥ 85% |
| **Over-correction rate** | `over_correction_rate` | Of the 30 items labelled `false`, the share the system wrongly judged `true`. **Lower is better** | ≤ 15% |
| Correction validity | `correction_validity` | 40 items rated by hand on the three-point scale in §6 | ≥ 85% valid |
| Rater agreement | `rater_agreement` | Of 20 items rated by both the author and a second native speaker, the share receiving the same rating | ≥ 80% |
| Retrieval hit rate | `retrieval_hit_rate` | Share of learner sentences for which a genuinely relevant grammar article appeared in the top 3 | ≥ 80% |
| Level compliance | `level_compliance_rate` | Share of AI replies containing no more over-level words than the threshold | ≥ 90% |
| Format compliance | `format_compliance_rate` | Share of outputs that were valid JSON **and** whose reason was in English. **Reported separately from accuracy** so a language slip is never mistaken for a reasoning error | — |
| Latency | `latency_ms` | Median and 95th percentile, **reported separately with and without the speech stages** | Before/after comparison |
| Adoption | — | Number of testers holding at least one session, and turns per tester | ≥ 5 testers |

**The corrected sentence is never scored by exact match.** Natural phrasing is not unique, so
exact matching would report far below true performance. Only the binary label is machine-scored;
the quality of the phrasing and reason is judged by eye (§6).

**Every published number carries `n` and an error margin** — e.g. "92% (n=40, ±8pt)".
On a 40-item test split the margin is roughly ±8 points, and stating that plainly earns more
trust than a large number does.

---

## 6. Correction validity rating scale

Applied by hand to 40 items; 20 of them are rated independently by a second native speaker.

| Rating | Meaning |
|---|---|
| **Valid** (妥当) | The corrected sentence is what a native would say, and the English reason is accurate and useful to a beginner |
| **Insufficient** (不十分) | The correction is acceptable but the reason is vague, generic, or does not explain the actual problem |
| **Wrong** (誤り) | The corrected sentence is unnatural or changes the meaning, or the reason is factually incorrect |

`correction_validity` counts **Valid** only.

---

## 7. Evaluation process terms

| Term | Definition |
|---|---|
| **Dev split** (`dev`) | 80 items. Prompts and thresholds are tuned against these, freely |
| **Test split** (`test`) | 40 items. Touched at the start and at the end of August, never in between. Tuning against these would make every number self-graded and worthless |
| **Baseline** (`baseline`) | The naive implementation: one LLM call saying "correct this Japanese and explain why". Measured **before** the real implementation exists, so the comparison table is honest |
| **Run record** (`run_record`) | JSON written on every evaluation run: model name, prompt version, date, split, **item count (`n`)**. README numbers cite which run they came from. **Without `n` there is no way to recover later how large a measurement a given README figure came from** (§5 requires `n` alongside every published figure) |
| **Rewrite-too-far** (書き換えすぎ) | A "correction" whose edit distance from the original exceeds the threshold. It is a different sentence, not a correction, and is discarded by the validation node |
| **Improvement cycle** | One documented loop of: measured a number, changed something specific, measured again. At least one is required in the README |

### Thresholds

Values live in [`config/thresholds.toml`](../../config/thresholds.toml), with the reasoning for
each. **Never inline them in code.** Current state:

| Threshold | Provisional value | Status |
|---|---|---|
| Rewrite-too-far, normalised edit distance | `0.65` | Provisional — confirm against the dev split in Week 2 |
| Rewrite-too-far, short-sentence absolute distance | `6` chars, applied below 8 chars | Provisional |
| Over-level content-word ratio | `0.2` | Provisional |
| Absolute tier gap rejected outright | `2` tiers | Provisional |
| Maximum regenerations per reply | `1` | Fixed — an unbounded loop would stall the conversation |

**The rewrite-too-far threshold is the one to be careful with.** Corrections into polite form
append long fixed endings to short sentences, so they score high on a normalised ratio even
though they are the most common and most clearly correct corrections this app produces.
Measured on 2026-08-02:

| Original | Corrected | Normalised distance |
|---|---|---|
| ありがとう | ありがとうございます | **0.50** |
| おはようです | おはようございます | 0.44 |
| 明日行くです | 明日行きます | 0.33 |

A threshold of 0.5 — the value most people would reach for first — would silently discard
`ありがとう → ありがとうございます`. **A discarded valid correction never reaches the learner
and never appears in the metrics**, so this failure mode is invisible unless looked for.
Week 2 must count how many valid dev-split corrections the threshold discards.
