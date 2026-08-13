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

- **The floor at B is です, ます or ください — not a fully polite sentence.** 「これ、ください」
  clears it and is `false`. 「トイレはどこ？」 and 「名前は？」 have none and are `true`
- **「お」 on its own does not clear the floor at B (revised 2026-08-08).** The floor first read
  "one of お / ください / です / ます", and verification did not bear that out. **「お仕事、何？」 has
  「お」 and is `true`**, corrected to 「お仕事は何でしょうか？」. **「お」 makes a word polite; it does
  not make the sentence polite** — the ending does.
  - **The exception is a sentence left unfinished.** 「お名前は。」 trails off rather than closing,
    and that form is polite in itself, so it clears the floor (this is eval-022's correction).
    **Closing on 「何？」 is not that form and does not clear it.**
  - **The other exception is a fixed greeting (added 2026-08-09).** 「はじめまして」 ends in none of
    です / ます / ください and does not trail off, but **it has no polite form of its own**, so the
    floor cannot be asked of it. **This is eval-017's own correction** — until this was written
    down, the floor rule contradicted the dataset's own answer.
    - **Do not widen the exception.** Counting all 120 items, the only sentences at tiers B and C
      that do not end in a polite form are 「はじめまして」 and 「お名前は」; tier C has none.
      **"It is a set phrase" only excuses a word that has no polite form at all** — 「ごめん」 has
      「すみません」, so it does not qualify.
  - **No label moved because of this revision** — only the verdict on 「お仕事、何？」 and the
    wording of the floor.
- **Plain form is `true` at C** because, as in §3, these are the scenes where controlling
  politeness actually starts to matter
- **At A, politeness alone is never a reason to label `true`.** There, `true` comes only from
  a grammatical error, a phrasing no native speaker would use, or an altered fixed phrase
- **A fixed phrase aimed in the wrong direction is a misused fixed phrase, not a politeness
  level.** Saying 「ご苦労さまです」 to a superior is `true` at tier A too
- **C asks for です・ます, not for full honorific and humble forms.** 「少し考えます」 to a manager
  is `false`
- **But at C, です・ます is only enough for the SPEAKER'S OWN action (decided 2026-08-08). A
  sentence that asks a manager to do something, or asks whether they will, needs an honorific
  or a request form (`ご〜ください` / `〜ていただけますか`), not just です・ます.**
  「この資料、確認しますか」 is `true`, and the correction is 「この資料をご確認いただけますか」. 「少し考えます」
  above stays `false` because that is the speaker's own action; the two rules do not conflict
  - **Without this distinction, the same politeness level in the same scene lands on both
    labels.** That is what happened: the machine pre-screen read §2 literally ("です・ます is
    enough") and put 「この資料、確認しますか」 on `false`; native verification overturned it
  - **Corrections for requests go up to the same level.** 「資料を見せて」 is corrected to
    「資料を見せていただけますか」, not 「資料を見せてください」 — 「ください」 still commands the listener's
    action, which is not enough for a manager
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
are never ingested. Difficulty tiers are built here, by cutting the **BCCWJ word frequency list
(Balanced Corpus of Contemporary Written Japanese, NINJAL)** at fixed points of cumulative
content-word coverage — see [`nlp/frequency.py`](../../nlp/frequency.py). The mapping is an
approximation and the README says so.

**This previously read "derived from word frequency in SudachiDict", which was wrong (corrected
2026-08-11).** SudachiPy exposes surface, lemma, reading and part of speech and **nothing about how
common a word is**; the dictionary ships compiled, and the CSV holding the cost column is not in the
package. **Tokenization comes from SudachiPy and frequency from BCCWJ** — two sources, not one.

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
| Detection accuracy | `detection_accuracy` | Of the 91 items labelled `true`, the share the system also judged `true` | ≥ 85% |
| **Over-correction rate** | `over_correction_rate` | Of the 29 items labelled `false`, the share the system wrongly judged `true`. **Lower is better** | ≤ 15% |
| Correction validity | `correction_validity` | 40 items rated by hand on the three-point scale in §6 | ≥ 85% valid |
| Rater agreement | `rater_agreement` | Of 20 items rated by both the author and a second native speaker, the share receiving the same rating | ≥ 80% |
| Retrieval hit rate | `retrieval_hit_rate` | Of the **16 items that have a grounding article**, the share for which one of the hand-annotated articles appeared in the top 3. **Does not read `score_min`** — rank only | ≥ 80% |
| Retrieval abstention rate | `retrieval_abstention_rate` | Of the **4 items no article covers**, the share for which nothing came back above `score_min`. **Depends on `score_min`**, so it is never added to the hit rate | Reported, no target |
| Level compliance | `level_compliance_rate` | Share of AI replies containing no more over-level words than the threshold. **Reported as two figures, first-shot and post-regeneration** (below) | ≥ 90% **on the post-regeneration figure** |
| Format compliance | `format_compliance_rate` | Share of outputs that were valid JSON **and** whose reason was in English. **Reported separately from accuracy** so a language slip is never mistaken for a reasoning error | — |
| Latency | `latency_ms` | Median and 95th percentile, **reported separately with and without the speech stages** | Before/after comparison |
| Adoption | — | Number of testers holding at least one session, and turns per tester | ≥ 5 testers |

**The corrected sentence is never scored by exact match.** Natural phrasing is not unique, so
exact matching would report far below true performance. Only the binary label is machine-scored;
the quality of the phrasing and reason is judged by eye (§6).

**`retrieval_hit_rate` is reported over 16 items, not 20 (decided 2026-08-13).** Of the twenty
measurement items annotated by hand, **four turned out to have no article that covers them** —
nothing in the reference states the polite negative past of a verb, the causative, adverb choice,
or 〜んです. Running the measurement without first deciding how those four are counted means
deciding it after seeing the result, because all three candidate rules break something that was
already pre-registered:

| Candidate | What it breaks |
|---|---|
| A `none` item is automatically a miss | The ceiling becomes **16/20 = 80.0%**, so the "≥ 80%" target is reachable only on a flawless run |
| Drop them from the denominator without saying so | `n = 20` is pre-registered in design.md; going quietly to 16 is a change made afterwards |
| "Hit if nothing came back above `score_min`", added into one figure | **Invariance to `score_min` is lost.** That invariance is the only thing stopping `score_min` from being tuned to flatter `over_correction_rate`; merged, one threshold moves the published rate by up to 20 points |

**So they are reported as two numbers.** The hit rate is measured over the **16 items that have a
ground**, reads rank only, and therefore does not move when `score_min` does. The four are
reported as `retrieval_abstention_rate`, **explicitly marked as depending on `score_min`**. The
two are never added together, and both `n`s go in the README.

**`level_compliance_rate` is reported as two figures (decided 2026-08-11).** The validation node
regenerates a reply that fails **this same check, through this same function**, so the
post-regeneration figure converges on "the share that fails twice in a row" and climbs past 90%
regardless of whether the replies are actually within reach of a beginner. A metric satisfied by
the machinery built to satisfy it is a metric **reported without being measured** — the same trap
week 1 avoided by not using constrained decoding.

| Figure | What it is | Target |
|---|---|---|
| **First-shot rate** | **Reply quality before any gate.** The headline figure in the README | None — reported for information |
| Post-regeneration rate | The operational figure | **≥ 90% attaches here** |

**The README states alongside it that the post-regeneration figure is the result of gating with
the same function, and so is not independent evidence.** It is measured on a fixed script (6 scenes
× 5 turns × 3 levels = 90 replies) which **contains no line from the evaluation set**, so that no
`test` sentence is ever pushed through the conversation prompt. Where the vocabulary tiers come
from is documented in [`nlp/frequency.py`](../../nlp/frequency.py).

**The 20 items for `rater_agreement` are taken from `dev` (decided 2026-08-08).** The
definition above does not say which split. Taking them from `test` would mean the author reading
test items in order to rate them, and **every prompt adjustment from week 2 onward would be
contaminated by that memory** (§7). Agreement asks whether two people read the scale the same
way, and `dev` carries that just as well.

- **Choose from the items where the baseline returned `needs_correction: true` and produced
  both a corrected sentence and an English reason.** The §6 scale looks at exactly those two
  things, so an item missing either **cannot be rated at all**. Including one leaves that item
  blank on both raters' forms and then counts as agreement
- **Spread the choice across the scenes.** The run record is ordered by scene, so the first 20
  run out inside the earlier scenes and **never reach `delay_notice` or `workplace_keigo`**.
  Those two are tier C (§2), and **the politeness floor — the part two raters most easily read
  differently — would then never be measured**
- **The rater sees neither the label nor the reference correction.** Showing either measures how
  well they can read the evaluation data. What they get is the learner's sentence, the system's
  correction, the system's reason, and **the situation the system itself was given**

**"The reason came back in English" is decided by proportion, not by presence (decided
2026-08-06).** Japanese inside quotes (「」 or quotation marks) is removed first, and what
remains counts as English if little Japanese is left. `The masu-stem of the verb (遅れ) cannot
end a sentence.` is English; `これは丁寧な言い方ではありません` is not. The threshold is
`reason_language` in [`config/thresholds.toml`](../../config/thresholds.toml) (§7).

- **The first implementation flagged any Japanese at all outside quotes, and it did not hold
  up.** On the day 4 baseline run (`test`, n=20) it flagged nine items, and **all nine were
  English explanations**; not one answer came back in Japanese. `format_compliance_rate` read
  55%, which a README reader takes to mean "45% answered in Japanese". None did
- **Quoting style must not be measured under the name of a language metric.** That is the
  "language mix-up" trap from the llm-jp-eval critique, pointed the other way (PLAN.md §2-4)
- Items that left Japanese outside quotes are still recorded per item in the run record
  (`japanese_left_unquoted`) but **never counted** in the metric: the correction prompt asks
  for 「」 and the baseline prompt does not, so the difference stays visible

**Every published number carries `n` and an error margin** — e.g. "92% (n=27, ±13pt)".
Stating it plainly earns more trust than a large number does.

**`n` is the metric's own denominator, not the size of the split (corrected 2026-08-09).**
This said "on a 40-item test split the margin is roughly ±8 points", and **no metric here has
40 in its denominator.** The two metrics are measured on different labels, so the split divides:

| Metric | Denominator in `test` | One item is worth | Rough margin |
|---|---|---|---|
| `detection_accuracy` | 27 (`true`) | 3.7pt | ±13pt |
| `over_correction_rate` | **13** (`false`) | **7.7pt** | **±19–27pt** |

With 13 items behind it, one item moves `over_correction_rate` 7.7 points and the 15% target is
really a two-item target. **Do not widen the denominator with `dev`.** Eighty of the 120 items
are `dev` — the side §7 allows tuning against — so once week 2 tunes the prompt, a
dev-inclusive figure rises by however much it was tuned. **Publish the `test` figure (`n=13`,
±19–27pt) and publish the width with it.** A `dev` figure may sit beside it only if it is
labelled as the tuned-on side, and the two are never added together.

**The answer to a thin denominator is more `false` items, not a mixed one** — which is what
the 250-item expansion in September is for.

---

## 6. Correction validity rating scale

`correction_validity` is applied by hand to 40 `test` items.

**The 20 items rated by a second native speaker are not a subset of those 40; they are chosen
separately from `dev`** (decided 2026-08-08 — the reasoning is in §5). Hand-rating therefore
covers 60 items in total. **This corrects an earlier "20 of them"** — once `rater_agreement`
was fixed to `dev`, the 20 stopped being a subset of the 40.

| Rating | Meaning |
|---|---|
| **Valid** (妥当) | The corrected sentence is what a native would say, and the English reason is accurate and useful to a beginner |
| **Insufficient** (不十分) | The correction is acceptable but the reason is vague, generic, or does not explain the actual problem |
| **Wrong** (誤り) | The corrected sentence is unnatural or changes the meaning, or the reason is factually incorrect |

`correction_validity` counts **Valid** only.

**The three grades assume a correction was needed (added 2026-08-09).** Rating the 20 items on
8/9 turned up **two ways for that assumption to fail**. Neither has a box, and **left undefined
each one splits raters between `Insufficient` and `Wrong`** — the corrected sentence itself is
natural, which reads as Valid, while the AI touched something that did not need touching, which
reads as Wrong.

> **The first rater's answers are published.** Not "not hidden here" — **not hidden at all**
> (established 2026-08-09, amended 8/10). `evals/rater/20260808-2041-rater-kit-jun.json` is
> committed with all twenty grades in it, because the evidence that it was sealed before the
> second rater replied *is* its commit timestamp. Recording only the counts in this section is
> therefore worth very little; `.steering/` names the three items outright.
>
> **So what protects `rater_agreement` is that the second rater is unlikely to go looking**,
> which is not a mechanism. **Read the number with that caveat attached.**
>
> **Procedure for the next kit:** commit a hash of the answers to timestamp the seal, and commit
> the answers themselves only after `rater_agreement` has been computed. This time that was not
> possible because "seal it" had already been defined as "commit the file".

**Case 1: nothing needed correcting at all** (**2** of the 20 rated on 8/9).

| When the original was already correct | Rating |
|---|---|
| The corrected sentence is natural in itself (a paraphrase) | **Insufficient** |
| The corrected sentence is unnatural or changes the meaning | **Wrong** |

**Case 2: something did need correcting, and the AI changed more than that** (**1** of the 20).

| When the necessary correction is present | Rating |
|---|---|
| What it added is also natural and still a version of what the learner said | **Insufficient** |
| What it added makes the sentence unnatural, or no longer a version of the learner's | **Wrong** |

In shape: a sentence missing one particle gets the particle supplied **and its verb swapped for a
different one**. **If the necessary correction is right, grade Insufficient** — punishing the
surplus as Wrong turns the scale into a measure of how much was changed rather than of how good
the correction is.

**Settled by convention rather than by a fourth box.** A four-grade scale would no longer match
the form printed on 8/8 or the copy in the second rater's hands. **The same wording is printed on
the rater's instructions** (`scale_note()` in `evals/rater_kit.py`, which renders one source for
both the paper form and the message; only the capitalisation of the grades differs).

**Case 2 is invisible to `over_correction_rate`.** That metric counts only corrections made to
items labelled `needs_correction: false`, and in case 2 the learner's sentence really was wrong.
"Over-correction is already counted elsewhere, so the scale need not punish it twice" holds for
case 1 only.

---

## 7. Evaluation process terms

| Term | Definition |
|---|---|
| **Dev split** (`dev`) | 80 items. Prompts and thresholds are tuned against these, freely |
| **Test split** (`test`) | 40 items. Touched at the start and at the end of August, never in between. Tuning against these would make every number self-graded and worthless |
| **Baseline** (`baseline`) | The naive implementation: one LLM call saying "correct this Japanese and explain why". Measured **before** the real implementation exists, so the comparison table is honest |
| **Run record** (`run_record`) | The JSON written for every measurement. It carries **enough to reconstruct the conditions a number came from**: model, prompt version, **scorer version** (`scorer_version`), **dataset version** (`items_digest`), **threshold version** (`thresholds_digest`), **stage** (`stage`), date, split and **item count** (`n`). Compliance runs add the **script version** (`script_digest`). Every README figure names the run it came from. **Without `n`, a figure in the README cannot be traced to the size of the measurement behind it** (§5 requires `n` beside every published number). **The scorer version is needed too** — a number that moved because a scoring rule changed reads as a change in the model if only the prompt version is visible (added 2026-08-06). **So are the dataset and threshold versions**: the improvement cycle changes one thing and writes two records, and if that thing was a threshold, **the two records are identical in every other field** (added 2026-08-12) |
| **Rewrite-too-far** (書き換えすぎ) | A "correction" whose edit distance from the original exceeds the threshold. It is a different sentence, not a correction, and is discarded by the validation node |
| **Improvement cycle** | One documented loop of: measured a number, changed something specific, measured again. At least one is required in the README |

### Thresholds

Values live in [`config/thresholds.toml`](../../config/thresholds.toml), with the reasoning for
each. **Never inline them in code.** Current state:

| Threshold | Provisional value | Status |
|---|---|---|
| Rewrite-too-far, normalised edit distance | **`0.85`** | **Fixed 2026-08-11.** Measured over the 73 corrections the baseline produced on `dev`: the **largest distance, 0.82, belonged to a correction identical to this project's own reference answer**, and the one correction that changed the meaning scored 0.77, below it. **No threshold separates them**, so it sits above the observed range and **a firing count of zero is reported** |
| Rewrite-too-far, short-sentence absolute distance | `6` chars, applied below 8 chars | Provisional |
| **Reason language: share of Japanese left outside quotes** | `0.25` | **Fixed — reconfirmed against the 80 dev items on 2026-08-11 and left where it was.** Across the 73 items that came back with a reason the share peaked at `0.164` and sat at `0.009` in the middle; **nothing crossed the threshold**. English explanations approach it from below (0.164 at most) and a reason actually written in Japanese sits far above (0.67–1.00 measured), so the threshold occupies the gap between them |
| Over-level content-word ratio | `0.2` | **Left as it was, 2026-08-11.** Across 90 replies regeneration would fire on 5.6% overall and 13.3% at beginner, under the 30% at which the prompt rather than the threshold is the thing to fix. **0.2 was never swept** — the measurement says this value does not break the conversation, not that it is the best one |
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
