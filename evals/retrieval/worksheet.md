# Which article should ground each item

## Who filled this in, and when — READ THIS BEFORE QUOTING THE HIT RATE

Filled by Claude (Opus) on **2026-08-13**, and **not yet reviewed line by line by
Jun**. No retrieval existed in this repository at the time — no index, no embedding
code, no dependency — so the order the metric depends on is intact, and that is
checkable from the git history rather than on trust: retrieval arrives on 8/15.

What this weakens has to be said wherever the number is published: the annotations
and the retrieval come from the same model family, so `retrieval_hit_rate` measures
agreement between an index and an annotator that is not independent of it. It is a
weaker claim than a human annotation would support. **Any line Jun changes on
review is worth more than the thirty as they stand.**

**A second, blind annotation was taken as a control.** A separate agent annotated
the same items from the articles alone, without seeing this sheet: **25 of 30 sets
matched exactly.** Four of the five disagreements were resolved in the second
annotator's favour and are marked in the git history of this file — one of them
(`eval-014`) because the article this sheet first cited states a rule the sentence
does not actually break.

**The order of what happened to `eval-052`, because it matters.** Annotating it
surfaced that the item contradicted `data/grammar/grammar-002`. Jun, a native
speaker, ruled on the article's side, so the item was relabelled `true` on
2026-08-13 and the article was made explicit about 「あります」. Relabelling redrew
the sample — `eval-056` left it and `eval-058` entered — and both were annotated
here before any search. The article's new example is **not** this item's sentence
and not its shape: a rule written from an item is a rule that answers that item.

Fill in `grounds:` for every item **before running any search**. More than one id is
fine — one topic is meant to be covered by more than one article. Write `none` if no
article covers it; that is a finding about the reference, not a blank.

The first block sets the retrieval threshold. The second is what the published hit
rate is measured on. Do not look at search results while filling either in.

## The rule being applied

List an article when it **states the rule** — the one broken, for an item needing
correction, or the one that licenses the sentence, for an item that is already
natural. Do not list an article that merely mentions a word in the sentence: every
id added makes a hit easier to score, so a generous sheet reports a good index
whatever the index does.

`lexical_share` is how much of the sentence appears verbatim in one article, and
which article that is. It is not a hint and must not be read as one. Read the two
together: a high share **in the article you are about to write down** means the
item could have been found by matching characters, so its hit says less; a high
share in a different article means the opposite, because that overlap pulls
retrieval away from the right answer. No threshold is drawn on it — the shares are
disclosed per item and no subgroup rate is computed from them.

## Articles

- `grammar-001` — Places, directions and clock times: に, で, を, へ, から
- `grammar-002` — What the verb acts on (を), and what exists or is needed (が)
- `grammar-003` — は marks what the sentence is about
- `grammar-004` — Adjectives, and what です can and cannot carry
- `grammar-005` — Nouns that become verbs with する, and verbs that become nouns with こと
- `grammar-006` — ています — a state that holds right now
- `grammar-007` — The て-form: asking, thanking, and who is doing what
- `grammar-008` — How polite to be, and the phrases that are fixed

## Threshold-setting sample (not published)

### 1. eval-043 · delay_notice · needs correction

- learner: 私はオフィスでいます。
- corrected: 私はオフィスにいます。
- lexical_share: 0.40 (grammar-001)
- grounds: grammar-001

### 2. eval-001 · greeting · needs correction

- learner: スーパーに買い物します。
- corrected: スーパーで買い物します。
- lexical_share: 0.64 (grammar-001)
- grounds: grammar-001

### 3. eval-013 · self_introduction · needs correction

- learner: 二年間前に来ました。
- corrected: 二年前に来ました。
- lexical_share: 0.44 (grammar-001)
- grounds: none

### 4. eval-036 · simple_request · needs correction

- learner: この服、試すことができますか。
- corrected: この服、試着できますか。
- lexical_share: 0.77 (grammar-005)
- grounds: grammar-005

### 5. eval-029 · thanks · needs correction

- learner: 忙しいから、運んでくれてありがとう。
- corrected: 忙しいのに、運んでくれてありがとう。
- lexical_share: 0.50 (grammar-007)
- grounds: none

### 6. eval-052 · workplace_keigo · needs correction

- learner: 部長、話したいことあります。
- corrected: 部長、話したいことがあります。
- lexical_share: 0.42 (grammar-005)
- grounds: grammar-002

### 7. eval-044 · delay_notice · needs correction

- learner: タクシーで行く。
- corrected: タクシーで行きます。
- lexical_share: 0.14 (grammar-001)
- grounds: grammar-008

### 8. eval-002 · greeting · needs correction

- learner: 私は毎朝六時起きます。
- corrected: 私は毎朝六時に起きます。
- lexical_share: 0.50 (grammar-001)
- grounds: grammar-001

### 9. eval-014 · self_introduction · needs correction

- learner: お仕事はなにしますか。
- corrected: お仕事は何ですか。
- lexical_share: 0.40 (grammar-005)
- grounds: grammar-006

### 10. eval-038 · simple_request · needs correction

- learner: これをいくらですか。
- corrected: これはいくらですか。
- lexical_share: 0.89 (grammar-003)
- grounds: grammar-003


## Measurement sample (the published hit rate)

### 11. eval-031 · thanks · needs correction

- learner: 荷物が持ってくれて、ありがとう。
- corrected: 荷物を持ってくれて、ありがとう。
- lexical_share: 0.71 (grammar-007)
- grounds: grammar-002

### 12. eval-053 · workplace_keigo · needs correction

- learner: 報告書はまだ書いていない。
- corrected: 報告書はまだ書いていません。
- lexical_share: 0.67 (grammar-008)
- grounds: grammar-008

### 13. eval-048 · delay_notice · needs correction

- learner: お待たせさせてすみませんでした。
- corrected: お待たせしてすみませんでした。
- lexical_share: 0.33 (grammar-002)
- grounds: none

### 14. eval-004 · greeting · needs correction

- learner: 良い一日。
- corrected: 良い一日を。
- lexical_share: 0.25 (grammar-001)
- grounds: grammar-008

### 15. eval-016 · self_introduction · needs correction

- learner: 私はエンジニアをします。
- corrected: 私はエンジニアをしています。
- lexical_share: 0.36 (grammar-001)
- grounds: grammar-005, grammar-006

### 16. eval-042 · simple_request · needs correction

- learner: すみません、トイレはどこ？
- corrected: すみません、トイレはどこですか。
- lexical_share: 0.55 (grammar-008)
- grounds: grammar-008

### 17. eval-085 · thanks · needs correction

- learner: たくさんありがとうございます。
- corrected: 本当にありがとうございます。
- lexical_share: 0.71 (grammar-008)
- grounds: none

### 18. eval-055 · workplace_keigo · needs correction

- learner: 資料を見せて。
- corrected: 資料を見せていただけますか。
- lexical_share: 0.67 (grammar-007)
- grounds: grammar-007, grammar-008

### 19. eval-103 · delay_notice · needs correction

- learner: もうすぐ着く。
- corrected: もうすぐ着きます。
- lexical_share: 0.33 (grammar-003)
- grounds: grammar-008

### 20. eval-005 · greeting · needs correction

- learner: 日曜日は走りませんかった。
- corrected: 日曜日は走りませんでした。
- lexical_share: 0.25 (grammar-002)
- grounds: none

### 21. eval-047 · delay_notice · already natural

- learner: あなた、どこですか。
- lexical_share: 0.38 (grammar-001)
- grounds: grammar-003

### 22. eval-009 · greeting · already natural

- learner: 良い朝ですね。
- lexical_share: 0.50 (grammar-003)
- grounds: grammar-008

### 23. eval-023 · self_introduction · already natural

- learner: どちらから来ましたか。
- lexical_share: 0.60 (grammar-001)
- grounds: grammar-001

### 24. eval-034 · simple_request · already natural

- learner: あなたはこの本を持っていますか。
- lexical_share: 0.47 (grammar-004)
- grounds: grammar-002, grammar-003

### 25. eval-032 · thanks · already natural

- learner: ありがとう、助かる。
- lexical_share: 0.62 (grammar-007)
- grounds: grammar-008

### 26. eval-058 · workplace_keigo · already natural

- learner: はい、分かりました。
- lexical_share: 0.50 (grammar-001)
- grounds: grammar-008

### 27. eval-050 · delay_notice · already natural

- learner: すみません、遅れます。
- lexical_share: 0.56 (grammar-002)
- grounds: grammar-006

### 28. eval-010 · greeting · already natural

- learner: もう出かけるんですか。
- lexical_share: 0.30 (grammar-003)
- grounds: none

### 29. eval-083 · self_introduction · already natural

- learner: あなたは田中さんですか？
- lexical_share: 0.36 (grammar-003)
- grounds: grammar-003

### 30. eval-101 · simple_request · already natural

- learner: 見てもいいですか？
- lexical_share: 0.88 (grammar-007)
- grounds: grammar-007

