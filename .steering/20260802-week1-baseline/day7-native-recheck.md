# 書き換えた12件のネイティブ再検証（2026-08-09）

> **判定済み（2026-08-09）：12件とも書いたとおりで可。覆りゼロ。**
> `batch3-hand-authored-2026-08-09.json` は `verified: true` に更新済み。
> 以下は判定に使った用紙で、**未着手の作業ではない**。

**Jun 本人の作業。所要 25〜30分（1件2分）。**

8/9 の監査で12件を書き換えた。うち10件は**手で書いた新しい文**で、
生成 → ネイティブ検証という鎖から外れている（[batch3-hand-authored-2026-08-09.json](../../data/evaluation/candidates/batch3-hand-authored-2026-08-09.json) に `verified: false` で記録）。

## 進め方

1. **先に [docs/ja/glossary.md](../../docs/ja/glossary.md) §2 を読む**（3つの判定基準）
2. **下の12件を、この紙だけ見て判断する。** 差し替えた理由は**この文書に書いていない**——
   先に理由を読むと「そう言われればそう見える」になり、8/8 のネイティブ判定を
   事前検品の提案を伏せて行った意味が消える
3. 判断が終わってから `batch3-hand-authored-2026-08-09.json` の `native_check` を読み、
   **食い違ったものだけ**を design.md に書き足す

## 各件で見ること（この4つだけ）

| | 問い | 外れたときの直し方 |
|---|---|---|
| ① | **初級者がこの場面で実際に言いそうな文か** | 文ごと差し替え |
| ② | **書かれたとおりに読んで、誤っているか**（意図を推測しない） | **`false` に倒すなら、内訳が 90:30 から崩れる。** 別の `true` を1件足すか、この件を差し替える |
| ③ | **直した文は、その場面でネイティブが実際に言う文か**（文法的に正しい、では足りない） | 直しだけ差し替え |
| ④ | **理由は、実際に行った直しを説明しているか。規則として広すぎないか** | 理由だけ書き直し |

**迷ったら②は `false` に倒す**（§2）。**迷った旨を書き残す**——判断そのものより、
どこで迷ったかが第2週の基準の直しに効く。

**12件とも `dev`。** ラベルを動かすと `pytest tests/test_evaluation_items.py` が落ちるので、
**落ちたら内訳を戻してから閉じる**（落ちること自体は正しい動作）。

---

## 1. eval-005　（greeting / `dev`）

**場面（モデルに渡した文言）**：You are a neighbour the learner passes in the morning. Keep it short and warm.
**相手の第一声**：おはようございます。　／　**丁寧さの下限（段階A）**：A neighbour or a colleague. No polite form is required.

| 学習者の文 | **日曜日は走りませんかった。** |
|---|---|
| 直し | **日曜日は走りませんでした。** |
| 理由 | The past of 「〜ません」 is 「〜ませんでした」. 「ませんかった」 borrows the ending an い-adjective takes. |

① 言いそう　　可 ・ 否　　② 誤っている　　可 ・ 否（`false` に倒す）
③ 直しは自然　可 ・ 否　　④ 理由は正確　　可 ・ 否

メモ：

---

## 2. eval-012　（greeting / `dev`）

**場面（モデルに渡した文言）**：You are a neighbour the learner passes in the morning. Keep it short and warm.
**相手の第一声**：おはようございます。　／　**丁寧さの下限（段階A）**：A neighbour or a colleague. No polite form is required.

| 学習者の文 | **雨が降るたら、行きません。** |
|---|---|
| 直し | **雨が降ったら、行きません。** |
| 理由 | 「〜たら」 attaches to the past form, so 「降る」 becomes 「降ったら」. 「降るたら」 is not a form the verb has. |

① 言いそう　　可 ・ 否　　② 誤っている　　可 ・ 否（`false` に倒す）
③ 直しは自然　可 ・ 否　　④ 理由は正確　　可 ・ 否

メモ：

---

## 3. eval-013　（self_introduction / `dev`）

**場面（モデルに渡した文言）**：You are meeting the learner for the first time at a small gathering. Ask about their name, work or where they are from, one thing at a time.
**相手の第一声**：はじめまして。お名前は何ですか。　／　**丁寧さの下限（段階B）**：Someone met for the first time, or a shop assistant. The sentence has to end in 「です」, 「ます」 or 「ください」, but it does not have to be polite throughout. 「お」 alone does NOT clear this floor — 「お仕事、何？」 needs correcting — unless the sentence trails off instead of closing, as 「お名前は。」 does.

| 学習者の文 | **二年間前に来ました。** |
|---|---|
| 直し | **二年前に来ました。** |
| 理由 | For years, months and days, 「〜前」 attaches to the bare number: 「二年前」. 「二年間」 is how long something lasted, not when it happened. |

① 言いそう　　可 ・ 否　　② 誤っている　　可 ・ 否（`false` に倒す）
③ 直しは自然　可 ・ 否　　④ 理由は正確　　可 ・ 否

メモ：

---

## 4. eval-029　（thanks / `dev`）

**場面（モデルに渡した文言）**：You are a colleague who has just helped the learner carry something heavy.
**相手の第一声**：どういたしまして。大丈夫でしたか。　／　**丁寧さの下限（段階A）**：A neighbour or a colleague. No polite form is required.

| 学習者の文 | **忙しいから、運んでくれてありがとう。** |
|---|---|
| 直し | **忙しいのに、運んでくれてありがとう。** |
| 理由 | 「から」 gives a cause. Thanking someone for doing something in spite of something else takes 「のに」. |

① 言いそう　　可 ・ 否　　② 誤っている　　可 ・ 否（`false` に倒す）
③ 直しは自然　可 ・ 否　　④ 理由は正確　　可 ・ 否

メモ：

---

## 5. eval-044　（delay_notice / `dev`）

**場面（モデルに渡した文言）**：You are a colleague waiting for the learner, who is running late. You are not annoyed.
**相手の第一声**：もしもし。今どちらですか。　／　**丁寧さの下限（段階C）**：A colleague being kept waiting, or a manager. 「です」/「ます」 is required. Honorific and humble keigo are NOT required.

| 学習者の文 | **タクシーで行く。** |
|---|---|
| 直し | **タクシーで行きます。** |
| 理由 | Said to the colleague who is waiting for you, the plain 「行く」 is too blunt. The polite form is 「行きます」. |

① 言いそう　　可 ・ 否　　② 誤っている　　可 ・ 否（`false` に倒す）
③ 直しは自然　可 ・ 否　　④ 理由は正確　　可 ・ 否

メモ：

---

## 6. eval-048　（delay_notice / `dev`）

**場面（モデルに渡した文言）**：You are a colleague waiting for the learner, who is running late. You are not annoyed.
**相手の第一声**：もしもし。今どちらですか。　／　**丁寧さの下限（段階C）**：A colleague being kept waiting, or a manager. 「です」/「ます」 is required. Honorific and humble keigo are NOT required.

| 学習者の文 | **お待たせさせてすみませんでした。** |
|---|---|
| 直し | **お待たせしてすみませんでした。** |
| 理由 | 「お待たせします」 already means keeping someone waiting. Adding 「させ」 makes it causative a second time. |

① 言いそう　　可 ・ 否　　② 誤っている　　可 ・ 否（`false` に倒す）
③ 直しは自然　可 ・ 否　　④ 理由は正確　　可 ・ 否

メモ：

---

## 7. eval-059　（workplace_keigo / `dev`）

**場面（モデルに渡した文言）**：You are the learner's manager at a Japanese company. You speak politely and expect polite speech in return, but you are not harsh.
**相手の第一声**：お疲れさまです。少しいいですか。　／　**丁寧さの下限（段階C）**：A colleague being kept waiting, or a manager. 「です」/「ます」 is required. Honorific and humble keigo are NOT required.

| 学習者の文 | **部長に呼びました。** |
|---|---|
| 直し | **部長に呼ばれました。** |
| 理由 | Being called by someone takes the passive 「呼ばれました」. 「呼びました」 says you did the calling. |

① 言いそう　　可 ・ 否　　② 誤っている　　可 ・ 否（`false` に倒す）
③ 直しは自然　可 ・ 否　　④ 理由は正確　　可 ・ 否

メモ：

---

## 8. eval-085　（thanks / `dev`）

**場面（モデルに渡した文言）**：You are a colleague who has just helped the learner carry something heavy.
**相手の第一声**：どういたしまして。大丈夫でしたか。　／　**丁寧さの下限（段階A）**：A neighbour or a colleague. No polite form is required.

| 学習者の文 | **たくさんありがとうございます。** |
|---|---|
| 直し | **本当にありがとうございます。** |
| 理由 | 「たくさん」 counts things. How much you mean it is 「本当に」 or 「どうも」. |

① 言いそう　　可 ・ 否　　② 誤っている　　可 ・ 否（`false` に倒す）
③ 直しは自然　可 ・ 否　　④ 理由は正確　　可 ・ 否

メモ：

---

## 9. eval-086　（thanks / `dev`）

**場面（モデルに渡した文言）**：You are a colleague who has just helped the learner carry something heavy.
**相手の第一声**：どういたしまして。大丈夫でしたか。　／　**丁寧さの下限（段階A）**：A neighbour or a colleague. No polite form is required.

| 学習者の文 | **今日はお世話しました。** |
|---|---|
| 直し | **今日はお世話になりました。** |
| 理由 | 「お世話する」 is what you do for someone else. Thanking someone who looked after you, it is 「お世話になりました」. |

① 言いそう　　可 ・ 否　　② 誤っている　　可 ・ 否（`false` に倒す）
③ 直しは自然　可 ・ 否　　④ 理由は正確　　可 ・ 否

メモ：

---

## 10. eval-095　（simple_request / `dev`）

**場面（モデルに渡した文言）**：You work at a small shop and the learner is a customer who needs something.
**相手の第一声**：いらっしゃいませ。何かお探しですか。　／　**丁寧さの下限（段階B）**：Someone met for the first time, or a shop assistant. The sentence has to end in 「です」, 「ます」 or 「ください」, but it does not have to be polite throughout. 「お」 alone does NOT clear this floor — 「お仕事、何？」 needs correcting — unless the sentence trails off instead of closing, as 「お名前は。」 does.

| 学習者の文 | **コーヒーを二枚ください。** |
|---|---|
| 直し | **コーヒーを二杯ください。** |
| 理由 | Cupfuls are counted with 「〜杯」. 「〜枚」 counts flat things such as sheets of paper and plates. |

① 言いそう　　可 ・ 否　　② 誤っている　　可 ・ 否（`false` に倒す）
③ 直しは自然　可 ・ 否　　④ 理由は正確　　可 ・ 否

メモ：

---

## 11. eval-001　（greeting / `dev`）

> **直しと理由だけを変えた（学習者の文は Day 3 のまま）。**③と④だけ見ればよい。

**場面（モデルに渡した文言）**：You are a neighbour the learner passes in the morning. Keep it short and warm.
**相手の第一声**：おはようございます。　／　**丁寧さの下限（段階A）**：A neighbour or a colleague. No polite form is required.

| 学習者の文 | **スーパーに買い物します。** |
|---|---|
| 直し | **スーパーで買い物します。** |
| 理由 | The place where an action happens takes 「で」, not 「に」. |

① 言いそう　　可 ・ 否　　② 誤っている　　可 ・ 否（`false` に倒す）
③ 直しは自然　可 ・ 否　　④ 理由は正確　　可 ・ 否

メモ：

---

## 12. eval-091　（thanks / `dev`）

> **理由だけを変えた（学習者の文と直しは Day 5 のまま）。**③と④だけ見ればよい。

**場面（モデルに渡した文言）**：You are a colleague who has just helped the learner carry something heavy.
**相手の第一声**：どういたしまして。大丈夫でしたか。　／　**丁寧さの下限（段階A）**：A neighbour or a colleague. No polite form is required.

| 学習者の文 | **あなたのお手伝いはとても大きかった。** |
|---|---|
| 直し | **手伝ってくれて、本当に助かった。** |
| 理由 | "Your help was very big" translated word for word. Japanese names what the person did rather than measuring it: 「手伝ってくれて助かった」. |

① 言いそう　　可 ・ 否　　② 誤っている　　可 ・ 否（`false` に倒す）
③ 直しは自然　可 ・ 否　　④ 理由は正確　　可 ・ 否

メモ：

---
