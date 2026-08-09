# Day 7（8/9 日）Minna Shuugou の持ち物と段取り

**8月の開催はこの回だけ**（次は 9/13）。**10:00 開始・家を 9:30 に出る。**
アプリの作業より、**8/9 でしかできないこと**を優先する。

---

## 1. 持ち物

| # | もの | 備考 |
|---|---|---|
| 1 | **採点キット（印刷）2部** | [evals/rater/20260808-2041-rater-kit.md](../../evals/rater/20260808-2041-rater-kit.md)。1部は予備。**印刷は 8/8 中に済ませる** |
| 2 | ボールペン 2本 | 相手に渡す用と自分用。鉛筆にしない（消えると採点が復元できない） |
| 3 | 連絡先を控えるもの | 紙とペンで足りる。スマホだけにしない（電池切れで全部消える） |
| 4 | スマホ（充電100%・モバイルバッテリー） | WhatsApp の交換に要る |
| 5 | テキスト版を開いた画面 | https://nihongo-coach.streamlit.app/ 。**通信が無くても成立する段取りにしてある**（下記） |

**アプリは見せなくても成立する。** 採点キットは紙で完結するので、
**会場の通信状況に依存させない。**

---

## 2. 会場で聞くこと — 3つに絞る

対面で話せる時間は短い。**その場で考えると、第二採点者の依頼が後回しになって終わる。**

1. **第二採点者を1人確保する**（最優先）— 日本語ネイティブ。所要30分。**その場で採点まで行く**
2. **テスター候補に声をかける**（目標5人以上）— 日本語を学んでいる人
3. **連絡先（WhatsApp）を控える** — 第3週は個別のアクセスコード付きリンクを配る

**確保できてもその場で採点まで行かない場合は、承諾だけ持ち帰る**（後日 WhatsApp で回収）。
**採点者ゼロで帰らない** — 8月に次の回は無く、第4週の `correction_validity` が独りの採点だけになる。

---

## 3. 1分の説明（英語・声に出して1回練習する）

> I'm building a speaking-practice app for people learning Japanese here in Bangalore.
> You talk to it, and after the conversation it tells you what you said wrong — with the
> reason in English, not in Japanese.
>
> The hard part isn't the talking. It's whether the corrections are actually right, and
> whether it stays quiet when your sentence was already fine. So I built a set of test
> sentences — 120 of them — and I measure both.
>
> Two things I'd love your help with. If you're a native Japanese speaker: could you look
> at 20 corrections and tell me whether each one is right? It takes about 30 minutes and
> I have it on paper here. And if you're learning Japanese: can I send you a link in two
> weeks when the speaking part works?

**テスターにはまだ配れない。** 第3週に個別のアクセスコード付きリンクを配る、と伝える。

---

## 4. 段取り

| 時刻 | やること |
|---|---|
| 〜9:30 | 朝の枠（2h）。持ち物の最終確認（0.25h）／1分の説明を声に出して1回（0.5h）／**土曜の積み残しの吸収（〜1.25h）**。**早く終わったら早く出る**（新しい作業を始めない） |
| 9:30 | 出発 |
| 10:00〜 | 会場。**まず第二採点者を探す。** 場が温まってからでは時間が無くなる |
| 採点中 | 相手が採点している30分の間にテスター候補へ声をかけ、連絡先を控える |
| 帰宅後 | 採点を JSON にして `rater_agreement` を計算 → 一致しなかった件を読む |

---

## 5. 帰宅後にやること（3h）

- [ ] 相手の採点を [20260808-2041-rater-kit-second.json](../../evals/rater/20260808-2041-rater-kit-second.json) に写す
      — **空の様式は生成済み。** `rating` に `valid` / `insufficient` / `wrong` を**小文字で**入れる
      （紙の様式は `Valid` と大文字で刷ってあるが、ファイルは小文字。**大文字のまま写すと計算が弾く**）
- [ ] `rater_agreement` を計算する（0.1h）
      ```
      .venv/bin/python -m evals.rater_kit --score \
        evals/rater/20260808-2041-rater-kit-jun.json \
        evals/rater/20260808-2041-rater-kit-second.json
      ```
      一致率と、**割れた件が採点キットの番号つきで出る**
- [ ] **一致しなかった件を読み、尺度のどこで解釈がずれたかを glossary §6 に書き戻す**
      — **一致率が低いときに直すのは尺度であって、相手の採点ではない。** ja → en を同じコミットに
- [ ] 記録欄（実績工数を含む）を [tasklist.md](tasklist.md) に埋める
- [ ] 「降ろす順番」の現在地を1行 [design.md](design.md) に書く

> **予備枠（0.75h）を作業で埋めない。** 対面の予定は延びるのが普通で、
> 埋めると 8/9 の遅れがそのまま第2週の初日に食い込む。

---

## 6. 自分の採点を先に封をする（8/8 中に終わらせる）

- ファイル: [evals/rater/20260808-2041-rater-kit-jun.json](../../evals/rater/20260808-2041-rater-kit-jun.json)
- §6 の3段階（`valid` / `insufficient` / `wrong`）で20件を採点する
- **相手の採点を見てから自分が採点すると一致率が無意味になる。** 8/9 まで開かない

**このファイルは Jun 本人が埋める。** 機械が埋めたら `rater_agreement` は
「ネイティブとモデルの一致率」になり、測りたいものではなくなる。
