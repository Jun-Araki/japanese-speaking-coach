# Which article should ground each item

Fill in `grounds:` for every item **before running any search**. More than one id is
fine — one topic is meant to be covered by more than one article. Write `none` if no
article covers it; that is a finding about the reference, not a blank.

The first block sets the retrieval threshold. The second is what the published hit
rate is measured on. Do not look at search results while filling either in.

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
- grounds: 

### 2. eval-001 · greeting · needs correction

- learner: スーパーに買い物します。
- corrected: スーパーで買い物します。
- grounds: 

### 3. eval-013 · self_introduction · needs correction

- learner: 二年間前に来ました。
- corrected: 二年前に来ました。
- grounds: 

### 4. eval-036 · simple_request · needs correction

- learner: この服、試すことができますか。
- corrected: この服、試着できますか。
- grounds: 

### 5. eval-029 · thanks · needs correction

- learner: 忙しいから、運んでくれてありがとう。
- corrected: 忙しいのに、運んでくれてありがとう。
- grounds: 

### 6. eval-053 · workplace_keigo · needs correction

- learner: 報告書はまだ書いていない。
- corrected: 報告書はまだ書いていません。
- grounds: 

### 7. eval-044 · delay_notice · needs correction

- learner: タクシーで行く。
- corrected: タクシーで行きます。
- grounds: 

### 8. eval-002 · greeting · needs correction

- learner: 私は毎朝六時起きます。
- corrected: 私は毎朝六時に起きます。
- grounds: 

### 9. eval-014 · self_introduction · needs correction

- learner: お仕事はなにしますか。
- corrected: お仕事は何ですか。
- grounds: 

### 10. eval-038 · simple_request · needs correction

- learner: これをいくらですか。
- corrected: これはいくらですか。
- grounds: 


## Measurement sample (the published hit rate)

### 11. eval-031 · thanks · needs correction

- learner: 荷物が持ってくれて、ありがとう。
- corrected: 荷物を持ってくれて、ありがとう。
- grounds: 

### 12. eval-055 · workplace_keigo · needs correction

- learner: 資料を見せて。
- corrected: 資料を見せていただけますか。
- grounds: 

### 13. eval-048 · delay_notice · needs correction

- learner: お待たせさせてすみませんでした。
- corrected: お待たせしてすみませんでした。
- grounds: 

### 14. eval-004 · greeting · needs correction

- learner: 良い一日。
- corrected: 良い一日を。
- grounds: 

### 15. eval-016 · self_introduction · needs correction

- learner: 私はエンジニアをします。
- corrected: 私はエンジニアをしています。
- grounds: 

### 16. eval-042 · simple_request · needs correction

- learner: すみません、トイレはどこ？
- corrected: すみません、トイレはどこですか。
- grounds: 

### 17. eval-085 · thanks · needs correction

- learner: たくさんありがとうございます。
- corrected: 本当にありがとうございます。
- grounds: 

### 18. eval-056 · workplace_keigo · needs correction

- learner: どうぞよろしく。
- corrected: どうぞよろしくお願いいたします。
- grounds: 

### 19. eval-103 · delay_notice · needs correction

- learner: もうすぐ着く。
- corrected: もうすぐ着きます。
- grounds: 

### 20. eval-005 · greeting · needs correction

- learner: 日曜日は走りませんかった。
- corrected: 日曜日は走りませんでした。
- grounds: 

### 21. eval-047 · delay_notice · already natural

- learner: あなた、どこですか。
- grounds: 

### 22. eval-009 · greeting · already natural

- learner: 良い朝ですね。
- grounds: 

### 23. eval-023 · self_introduction · already natural

- learner: どちらから来ましたか。
- grounds: 

### 24. eval-034 · simple_request · already natural

- learner: あなたはこの本を持っていますか。
- grounds: 

### 25. eval-032 · thanks · already natural

- learner: ありがとう、助かる。
- grounds: 

### 26. eval-052 · workplace_keigo · already natural

- learner: 部長、話したいことあります。
- grounds: 

### 27. eval-050 · delay_notice · already natural

- learner: すみません、遅れます。
- grounds: 

### 28. eval-010 · greeting · already natural

- learner: もう出かけるんですか。
- grounds: 

### 29. eval-083 · self_introduction · already natural

- learner: あなたは田中さんですか？
- grounds: 

### 30. eval-101 · simple_request · already natural

- learner: 見てもいいですか？
- grounds: 

